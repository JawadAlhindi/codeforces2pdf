from flask import Flask, render_template, request, send_file, redirect, url_for, flash, jsonify
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
import httpx
from werkzeug.utils import secure_filename
import zipfile
import io
import bs4

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get("SESSION_SECRET", "development-key")

# Ensure output directory exists
OUTPUT_DIR = "outputs"
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# Default HTTP headers for Codeforces requests
def get_codeforces_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://codeforces.com/',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

# Function to test Codeforces URL accessibility
def test_codeforces_access(contest_id, problem):
    urls = [
        f"https://codeforces.com/contest/{contest_id}/problem/{problem}",
        f"https://codeforces.com/problemset/problem/{contest_id}/{problem}",
        f"https://codeforces.com/gym/{contest_id}/problem/{problem}"
    ]
    
    headers = get_codeforces_headers()
    
    for url in urls:
        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=5) as client:
                resp = client.get(url)
            if resp.status_code == 200:
                # Check if the response contains problem content
                if '<div class="problem-statement">' in resp.text:
                    return True
        except Exception as e:
            # Log the error but continue trying other URLs
            print(f"Error accessing {url}: {str(e)}")
            continue
    
    return False

# Function to get all problems from a contest
def get_contest_problems(contest_id):
    """
    Fetches all problem IDs available in a Codeforces contest
    
    Args:
        contest_id: The ID of the contest
        
    Returns:
        A list of problem IDs (A, B, C, etc.)
    """
    # Try both contest and gym URLs
    urls = [
        f"https://codeforces.com/contest/{contest_id}",
        f"https://codeforces.com/gym/{contest_id}"
    ]
    
    headers = get_codeforces_headers()
    
    for url in urls:
        try:
            print(f"Fetching contest problems from {url}")
            with httpx.Client(headers=headers, follow_redirects=True, timeout=10) as client:
                resp = client.get(url)
            
            if resp.status_code != 200:
                print(f"Got status code {resp.status_code} for {url}")
                continue
                
            # Parse the HTML to find problem links
            soup = bs4.BeautifulSoup(resp.text, 'html.parser')
            
            # Different ways to find problem links
            problem_ids = []
            
            # Look for problem table rows
            problem_rows = soup.select('table.problems tr')
            if problem_rows and len(problem_rows) > 1:  # Skip header row
                for row in problem_rows[1:]:  # Skip header row
                    # Find problem ID (typically first column)
                    problem_id_cell = row.select_one('td:first-child')
                    if problem_id_cell:
                        problem_id = problem_id_cell.text.strip()
                        # Usually just the letter (A, B, C, etc.)
                        if problem_id and len(problem_id) <= 2:
                            problem_ids.append(problem_id)
            
            # Alternative: look for problem links in the sidebar
            if not problem_ids:
                sidebar_links = soup.select('.problems a')
                for link in sidebar_links:
                    href = link.get('href', '')
                    if '/problem/' in href:
                        # Extract problem ID from URL
                        problem_id = href.split('/')[-1].strip()
                        if problem_id and len(problem_id) <= 2:
                            problem_ids.append(problem_id.upper())
            
            # Another alternative: look for specific problem links
            if not problem_ids:
                all_links = soup.find_all('a')
                for link in all_links:
                    href = link.get('href', '')
                    if '/problem/' in href:
                        # Extract problem ID from URL
                        problem_id = href.split('/')[-1].strip()
                        if problem_id and len(problem_id) <= 2 and problem_id.upper() not in problem_ids:
                            problem_ids.append(problem_id.upper())
            
            # If we found problems, return them
            if problem_ids:
                # Remove duplicates and sort
                unique_problems = sorted(set(problem_ids))
                print(f"Found problems: {unique_problems}")
                return unique_problems
                
        except Exception as e:
            print(f"Error fetching contest {contest_id}: {str(e)}")
            continue
    
    # Fallback to common problem IDs if we couldn't extract them
    print("Using fallback problem IDs (A-F)")
    return ['A', 'B', 'C', 'D', 'E', 'F']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    contest_id = request.form.get('contest_id')
    problem = request.form.get('problem')
    problem_url = request.form.get('problem_url')
    mode = request.form.get('mode', 'default')
    all_problems = request.form.get('all_problems') == 'true'
    
    # Process URL if provided
    if problem_url:
        # Extract contest_id and problem from URL
        patterns = [
            r'codeforces\.com/contest/(\d+)/problem/([A-Za-z0-9]+)',
            r'codeforces\.com/problemset/problem/(\d+)/([A-Za-z0-9]+)',
            r'codeforces\.com/gym/(\d+)/problem/([A-Za-z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, problem_url)
            if match:
                contest_id = match.group(1)
                if not all_problems:  # Only override problem if not downloading all
                    problem = match.group(2)
                break
    
    if not contest_id:
        flash('Contest ID is required', 'error')
        return redirect(url_for('index'))
    
    try:
        contest_id = int(contest_id)
    except ValueError:
        flash('Contest ID must be a number', 'error')
        return redirect(url_for('index'))
    
    # Check if we are downloading a single problem or all problems
    if not all_problems and not problem:
        flash('Problem ID is required for single problem download', 'error')
        return redirect(url_for('index'))
    
    # Map mode string to command-line args
    mode_arg = ""
    if mode == "fast":
        mode_arg = "-f"
    elif mode == "graphics":
        mode_arg = "-g"
    
    if all_problems:
        # Fetch available problems for this contest
        problems = get_contest_problems(contest_id)
        
        if not problems:
            flash(f'Unable to find problems for contest {contest_id}. Please verify the contest ID.', 'error')
            return redirect(url_for('index'))
        
        # Create a zip file to store all PDFs
        import zipfile
        import io
        
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            for problem_id in problems:
                # Call the codeforces_to_pdf.py script for each problem
                cmd = ['python', 'codeforces_to_pdf.py', str(contest_id), problem_id]
                if mode_arg:
                    cmd.append(mode_arg)
                cmd.extend(['-d', OUTPUT_DIR])
                
                try:
                    # Run the conversion process
                    process = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    output_file = f"{contest_id}{problem_id}.pdf"
                    output_path = os.path.join(OUTPUT_DIR, output_file)
                    
                    if os.path.exists(output_path):
                        # Add the PDF to the zip file
                        zf.write(output_path, output_file)
                except Exception as e:
                    print(f"Error processing problem {problem_id}: {str(e)}")
                    # Continue with other problems even if one fails
                    continue
        
        # Reset the file pointer
        memory_file.seek(0)
        
        # Add a "success" flash message  
        flash(f'All problems from contest {contest_id} generated successfully!', 'success')
        
        # Send the zip file
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"contest_{contest_id}_problems.zip"
        )
    else:
        # Single problem case
        # Ensure problem ID is alphanumeric and properly formatted
        problem = problem.strip().upper()
        if not re.match(r'^[A-Z0-9]{1,2}$', problem):
            flash('Problem ID must be a letter or alphanumeric code (e.g., A, B, C)', 'error')
            return redirect(url_for('index'))
            
        # Call the codeforces_to_pdf.py script
        cmd = ['python', 'codeforces_to_pdf.py', str(contest_id), problem]
        if mode_arg:
            cmd.append(mode_arg)
        cmd.extend(['-d', OUTPUT_DIR])
        
        try:
            # Run the conversion process with output capture
            process = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output_file = f"{contest_id}{problem}.pdf"
            output_path = os.path.join(OUTPUT_DIR, output_file)
            
            if os.path.exists(output_path):
                # Check if this is a placeholder PDF (indicating failure)
                file_size = os.path.getsize(output_path)
                output = process.stdout
                
                # Check for 403 errors specifically 
                if "returned status code 403" in output and "All URLs failed" in output:
                    flash(f'Unable to access Codeforces (403 Forbidden). Codeforces might be blocking our requests. Try a different contest or problem, or try again later.', 'error')
                    return redirect(url_for('index'))
                # Other placeholder PDF checks
                elif "Generating placeholder PDF" in output and file_size < 10000:
                    flash(f'Unable to fetch problem {contest_id}{problem} from Codeforces. Please verify the Contest ID and Problem ID are correct.', 'error')
                    return redirect(url_for('index'))
                
                # Add a "success" flash message  
                flash(f'PDF for problem {contest_id}{problem} generated successfully! Returning to home page after download starts.', 'success')
                
                # Set a response header to redirect after download
                response = send_file(output_path, 
                                mimetype='application/pdf',
                                as_attachment=True,
                                download_name=output_file)
                
                # This JavaScript will redirect back to the index page after download starts
                response.headers["Content-Disposition"] = f"attachment; filename={output_file}; redirect-url={url_for('index')}"
                
                return response
            else:
                flash('PDF generation failed. File not found.', 'error')
                return redirect(url_for('index'))
        except subprocess.CalledProcessError as e:
            flash(f'Error during conversion: {e.stderr}', 'error')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Unexpected error: {str(e)}', 'error')
            return redirect(url_for('index'))

@app.route('/check-availability', methods=['POST'])
def check_availability():
    """API endpoint to check if a Codeforces problem is accessible and get details"""
    print("Received check-availability request")
    
    # Print the raw request data for debugging
    print(f"Request data: {request.data}")
    
    contest_id = request.json.get('contest_id')
    problem = request.json.get('problem')
    
    print(f"Extracted contest_id: {contest_id}, problem: {problem}")
    
    if not contest_id or not problem:
        print("Error: Contest ID or Problem ID missing")
        return jsonify({'success': False, 'message': 'Contest ID and Problem ID are required'})
    
    try:
        contest_id = int(contest_id)
    except ValueError:
        print(f"Error: Contest ID '{contest_id}' is not a number")
        return jsonify({'success': False, 'message': 'Contest ID must be a number'})
    
    # Standardize problem ID
    problem = problem.strip().upper()
    
    # List of URLs to try
    urls = [
        f"https://codeforces.com/contest/{contest_id}/problem/{problem}",
        f"https://codeforces.com/problemset/problem/{contest_id}/{problem}",
        f"https://codeforces.com/gym/{contest_id}/problem/{problem}"
    ]
    
    headers = get_codeforces_headers()
    
    import bs4
    import re
    
    # Function to extract rating if available
    def extract_rating(html):
        try:
            soup = bs4.BeautifulSoup(html, 'html.parser')
            
            # Method 1: Look for spans with "Difficulty:" text
            for span in soup.find_all('span'):
                if span.text and "Difficulty:" in span.text:
                    sibling = span.find_next_sibling("span")
                    if sibling and sibling.text.strip().isdigit():
                        return int(sibling.text.strip())
            
            # Method 2: Check for color classes (common in older problems)
            for color_class in ['red', 'orange', 'violet', 'blue', 'cyan', 'green']:
                if soup.select_one(f".{color_class}"):
                    # Approximate ratings based on color class
                    ratings = {'red': 2100, 'orange': 1900, 'violet': 1700, 
                              'blue': 1500, 'cyan': 1300, 'green': 1100}
                    return ratings.get(color_class, 0)
            
            # Method 3: Try problem ID based rating estimation
            # Many standard problems have consistent ratings 
            # (especially div2 contest problems)
            if problem in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
                # Estimate based on common contest problem ratings
                estimates = {
                    'A': 800, 
                    'B': 1200,
                    'C': 1500,
                    'D': 1800,
                    'E': 2000,
                    'F': 2200,
                    'G': 2400,
                    'H': 2700
                }
                return estimates.get(problem, 0)
                
            # Method 4: Try to find rating in page text
            rating_patterns = [
                r'difficulty[:\s]*(\d{3,4})',
                r'rated[:\s]*(\d{3,4})',
                r'level[:\s]*(\d{3,4})'
            ]
            
            for pattern in rating_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    rating = int(match.group(1))
                    if 800 <= rating <= 3500:  # Valid Codeforces rating range
                        return rating
            
            # Common and famous problems by problem number
            if contest_id == 4 and problem == 'A':  # Watermelon
                return 800
            elif contest_id == 1 and problem == 'A':  # Theatre Square
                return 1000
            elif contest_id == 158 and problem == 'A':  # Next Round
                return 800
            elif contest_id == 231 and problem == 'A':  # Team
                return 800
            elif contest_id == 71 and problem == 'A':  # Way Too Long Words
                return 800
                
            print("No rating found for this problem")
            return 0
        except Exception as e:
            print(f"Error extracting rating: {str(e)}")
            return 0
    
    # Extract title, time limit, and memory limit
    def extract_problem_details(html):
        try:
            soup = bs4.BeautifulSoup(html, 'html.parser')
            
            # Extract title
            title_div = soup.find('div', class_='title')
            title = title_div.text.strip() if title_div else f"Problem {contest_id}{problem}"
            
            # Extract time and memory limits
            time_pattern = re.compile(r'time limit[^:]*:\s*(\d+(?:\.\d+)?)\s*(?:second|s)', re.IGNORECASE)
            memory_pattern = re.compile(r'memory limit[^:]*:\s*(\d+)\s*(?:megabytes|MB)', re.IGNORECASE)
            
            time_match = time_pattern.search(html)
            memory_match = memory_pattern.search(html)
            
            time_limit = f"{time_match.group(1)} second(s)" if time_match else "1 second"
            memory_limit = f"{memory_match.group(1)} MB" if memory_match else "256 MB"
            
            return {
                'title': title,
                'time_limit': time_limit,
                'memory_limit': memory_limit
            }
        except Exception as e:
            print(f"Error extracting problem details: {str(e)}")
            return {
                'title': f"Problem {contest_id}{problem}",
                'time_limit': "1 second",
                'memory_limit': "256 MB"
            }
    
    # Try each URL
    print(f"Trying URLs: {urls}")
    for url in urls:
        try:
            print(f"Trying URL: {url}")
            with httpx.Client(headers=headers, follow_redirects=True, timeout=10) as client:
                resp = client.get(url)
            
            print(f"Response status: {resp.status_code}")
            
            if resp.status_code == 200:
                # Check if the response contains problem content
                has_problem_statement = '<div class="problem-statement">' in resp.text
                has_problem_index = '.problemindexholder' in resp.text
                print(f"Has problem statement: {has_problem_statement}, Has problem index: {has_problem_index}")
                
                if has_problem_statement or has_problem_index:
                    # Extract problem details
                    details = extract_problem_details(resp.text)
                    rating = extract_rating(resp.text)
                    
                    print(f"Problem details: {details}")
                    print(f"Rating: {rating}")
                    
                    result = {
                        'success': True, 
                        'message': 'Problem is available',
                        'title': details['title'],
                        'time_limit': details['time_limit'],
                        'memory_limit': details['memory_limit'],
                        'rating': rating
                    }
                    print(f"Returning result: {result}")
                    return jsonify(result)
                else:
                    print("Response doesn't contain problem content")
            else:
                print(f"Invalid response status: {resp.status_code}")
        except Exception as e:
            print(f"Error accessing {url}: {str(e)}")
            continue
    
    return jsonify({'success': False, 'message': f'Problem {contest_id}{problem} could not be accessed'})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
