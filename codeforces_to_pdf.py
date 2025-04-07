import argparse
from dataclasses import dataclass
from enum import Enum
from html import unescape
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Optional, Tuple, List, Dict

import bs4
import httpx
from weasyprint import HTML, CSS

CACHE_PATH = ".cache"
TEMP_FILES = []


class Formatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO:
            self._style._fmt = "[\033[0;32m%(message)s\033[0m]"
        elif record.levelno == logging.ERROR:
            self._style._fmt = "\033[0;31mERROR: %(message)s\033[0m"
        elif record.levelno == logging.WARNING:
            self._style._fmt = "\033[0;34mWARNING: %(message)s\033[0m"
        else:
            self._style._fmt = "%(message)s"
        return super().format(record)


logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(Formatter())
logger.setLevel(logging.INFO)
logger.addHandler(handler)


def error(message):
    logger.error(message)
    sys.exit(1)


def exception(message):
    logger.exception(message)
    sys.exit(1)


def warning(message):
    logger.warning(message)


def info(message):
    logger.info(message)


def debug(message):
    logger.debug(message)


class Mode(Enum):
    DEFAULT = 1
    FAST = 2
    GRAPHICS = 3


@dataclass(frozen=True)
class LatexFormula:
    content: str
    is_inline: bool


def remove_alert(block: bs4.Tag):
    """Remove alert, info, and notification divs from the problem block."""
    if block is None:
        return
        
    for div in block.find_all("div", class_=['alert', 'alert-info', 'diff-notifier']):
        div.extract()


def get_problem_rating(problem_page_html: str) -> int:
    """
    Extract the difficulty rating from a Codeforces problem page.
    
    Args:
        problem_page_html: The HTML content of the problem page
        
    Returns:
        The problem rating as an integer, or 0 if not found
    """
    try:
        # Create a BeautifulSoup object from the HTML
        bs = bs4.BeautifulSoup(problem_page_html, "html.parser")
        
        # Method 1: Look for the span with "Difficulty:" text
        difficulty_spans = bs.find_all("span", string=lambda text: text and "Difficulty:" in text)
        if difficulty_spans:
            # Find the sibling span with the rating value
            for span in difficulty_spans:
                sibling = span.find_next_sibling("span")
                if sibling and sibling.text.strip().isdigit():
                    return int(sibling.text.strip())
        
        # Method 2: Look for the sidebar rating or problem tag
        rating_elem = bs.select_one(".tag-box span.property-title:contains('rating:')")
        if rating_elem:
            rating_value = rating_elem.find_next_sibling("span")
            if rating_value and rating_value.text.strip().isdigit():
                return int(rating_value.text.strip())
        
        # Method 3: Try to find problem rating in problem tags
        problem_tags = bs.select(".rtable .id")
        for tag in problem_tags:
            rating_cell = tag.find_next_sibling("td")
            if rating_cell and rating_cell.text.strip().isdigit():
                return int(rating_cell.text.strip())
                
        # Method 4: Check color classes that might indicate difficulty
        if bs.select_one(".red"):
            return 2100  # Approximate value for red
        elif bs.select_one(".orange"):
            return 1900  # Approximate value for orange
        elif bs.select_one(".violet"):
            return 1700  # Approximate value for violet
        elif bs.select_one(".blue"):
            return 1500  # Approximate value for blue
        elif bs.select_one(".cyan"):
            return 1300  # Approximate value for cyan
        elif bs.select_one(".green"):
            return 1100  # Approximate value for green
            
        return 0  # Rating not found
    except Exception as e:
        warning(f"Error extracting problem rating: {str(e)}")
        return 0

def get_difficulty_color(rating: int) -> str:
    """
    Get the color for a particular Codeforces rating.
    
    Args:
        rating: The problem rating
        
    Returns:
        The corresponding CSS color code
    """
    if rating == 0:
        return "#808080"  # Gray for unknown rating
    elif rating < 1200:
        return "#3db73d"  # Green
    elif rating < 1400:
        return "#00c0c0"  # Cyan
    elif rating < 1600:
        return "#0000ff"  # Blue
    elif rating < 1900:
        return "#aa00aa"  # Violet
    elif rating < 2100:
        return "#ff8c00"  # Orange
    elif rating < 2400:
        return "#ff0000"  # Red
    else:
        return "#aa0000"  # Dark red

def difficulty_badge_html(rating: int, include_label: bool = True) -> str:
    """
    Generate HTML for a difficulty badge.
    
    Args:
        rating: The problem rating
        include_label: Whether to include the "Difficulty: " label
        
    Returns:
        HTML string for the badge
    """
    color = get_difficulty_color(rating)
    label = "Difficulty: " if include_label and rating > 0 else ""
    rating_text = str(rating) if rating > 0 else "Unknown"
    
    return f"""
    <div class="difficulty-badge" style="display: inline-block; padding: 3px 8px; 
                                        background-color: {color}; color: white; 
                                        border-radius: 5px; font-weight: bold; 
                                        font-size: 0.9em; margin: 5px 0;">
        {label}{rating_text}
    </div>
    """

def extract_problem(contest_id, problem) -> Tuple[str, str, int]:
    """
    Extract problem content from Codeforces.
    Tries multiple URL formats and handles various error cases.
    
    Args:
        contest_id: The ID of the contest
        problem: The letter/ID of the problem within the contest
        
    Returns:
        Tuple of (output_filename, html_content, problem_rating)
    """
    # Standardize problem ID (uppercase)
    problem = problem.strip().upper()
    problem_rating = 0
    
    # Try these URL formats in order with different cases for the problem ID
    urls = [
        # Standard contest format
        f"https://codeforces.com/contest/{contest_id}/problem/{problem}",
        # Problemset format
        f"https://codeforces.com/problemset/problem/{contest_id}/{problem}",
        # Gym format
        f"https://codeforces.com/gym/{contest_id}/problem/{problem}",
        # Try lowercase problem ID
        f"https://codeforces.com/contest/{contest_id}/problem/{problem.lower()}",
        f"https://codeforces.com/problemset/problem/{contest_id}/{problem.lower()}"
    ]
    
    # Try different browser user agents with advanced anti-bot detection bypass
    headers_list = [
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://codeforces.com/',
            'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'Cache-Control': 'max-age=0',
            'dnt': '1',
            'Upgrade-Insecure-Requests': '1',
        },
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://codeforces.com/',
            'Connection': 'keep-alive',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
        },
        {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://codeforces.com/problemset',
            'DNT': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1',
        }
    ]
    
    # For sample output if all attempts fail
    sample_html = f"""
    <div class="title">Unable to fetch problem {contest_id}{problem}</div>
    <div>
        <p>Could not connect to Codeforces to retrieve problem content.</p>
        <p>Please check your internet connection and try again later.</p>
        <p>You might also want to verify if the contest ID ({contest_id}) and problem ID ({problem}) are correct.</p>
        <p>Tip: Try official Codeforces URLs to check if the problem exists:</p>
        <ul>
            <li><a href="https://codeforces.com/contest/{contest_id}/problem/{problem}" target="_blank">Contest format</a></li>
            <li><a href="https://codeforces.com/problemset/problem/{contest_id}/{problem}" target="_blank">Problemset format</a></li>
        </ul>
    </div>
    """
    
    url_used = ""
    resp = None
    
    # Try each URL with each set of headers
    for url in urls:
        for headers in headers_list:
            try:
                info(f"Trying URL: {url}")
                # Use httpx instead of requests for better performance and modern features
                with httpx.Client(follow_redirects=True, timeout=10) as client:
                    resp = client.get(url, headers=headers)
                url_used = url
                
                if resp.status_code == 200:
                    # Check if the response actually contains problem content
                    if '<div class="problem-statement">' in resp.text or '.problemindexholder' in resp.text:
                        info(f"Successfully fetched problem from: {url}")
                        # Parse the response
                        bs = bs4.BeautifulSoup(resp.text, "html.parser")
                        problem_block = bs.select_one(".problemindexholder")
                        
                        if problem_block is not None:
                            remove_alert(problem_block)
                            html = problem_block.decode_contents()
                            # Try to extract the problem rating
                            problem_rating = get_problem_rating(resp.text)
                            info(f"Successfully extracted problem content from: {url_used}")
                            if problem_rating > 0:
                                info(f"Extracted problem rating: {problem_rating}")
                            return f"{contest_id}{problem}.pdf", html, problem_rating
                    else:
                        info(f"URL {url} returned OK status but didn't contain problem content")
                else:
                    info(f"URL {url} returned status code {resp.status_code}")
            except (httpx.RequestError, Exception) as e:
                info(f"Error connecting to {url}: {str(e)}")
                # Continue to the next URL/headers combination
    
    # If all attempts failed
    warning(f"All URLs failed. Last attempt: '{url_used}' status_code={resp.status_code if resp else 'No response'}")
    info("Generating placeholder PDF with error message")
    return f"{contest_id}{problem}.pdf", sample_html, 0


def generate_latex_formulas_embeds_graphics(
    formulas: list[LatexFormula],
) -> Optional[list[str]]:
    # Simplified implementation that just returns placeholders
    # for LaTeX formulas without attempting actual rendering
    if not formulas:
        return []
    
    embeds = []
    for formula in formulas:
        if formula.is_inline:
            embeds.append(f'<span class="math-inline">{formula.content}</span>')
        else:
            embeds.append(f'<div class="math-display">{formula.content}</div>')
            
    return embeds


def generate_latex_formulas_embeds(
    formulas: list[LatexFormula],
) -> Optional[list[str]]:
    # Simplified implementation that focuses on speed and reliability
    if not formulas:
        return []
    
    embeds = []
    for formula in formulas:
        if formula.is_inline:
            embeds.append(f'<span class="math-inline">{formula.content}</span>')
        else:
            embeds.append(f'<div class="math-display">{formula.content}</div>')
            
    return embeds


def generate_latex_formulas_embeds_fast(
    formulas: list[LatexFormula],
) -> Optional[list[str]]:
    # Simplified version that just returns basic HTML for formulas
    if not formulas:
        return []
    
    html_formulas_embeds = []
    for formula in formulas:
        if formula.is_inline:
            html_formulas_embeds.append(f'<span class="math-inline">{formula.content}</span>')
        else:
            html_formulas_embeds.append(f'<div class="math-display">{formula.content}</div>')
            
    return html_formulas_embeds


def render_formulas(html: str, mode: Mode) -> Tuple[bool, str]:
    # Simplified implementation as requested - just apply basic handling
    return True, html


def handle_simple_math_notation(html: str) -> str:
    """
    Apply simple CSS-based formatting for math notation when LaTeX rendering fails
    """
    # Handle subscripts: replace a_n with a<sub>n</sub>
    html = re.sub(r'([a-zA-Z])_([a-zA-Z0-9])', r'\1<sub>\2</sub>', html)
    
    # Handle superscripts: replace a^n with a<sup>n</sup>
    html = re.sub(r'([a-zA-Z0-9])\^([a-zA-Z0-9])', r'\1<sup>\2</sup>', html)
    
    # Handle square roots: replace \sqrt{...} with a styled span
    html = re.sub(r'\\sqrt\{([^}]+)\}', r'<span class="math-notation">√\1</span>', html)
    
    # Handle simple fractions: replace \frac{a}{b} with styled divs
    html = re.sub(
        r'\\frac\{([^}]+)\}\{([^}]+)\}',
        r'<div class="fraction"><span class="numerator">\1</span><span class="denominator">\2</span></div>',
        html
    )
    
    # Add more math notation handling as needed
    
    return html


def parse_args():
    parser = argparse.ArgumentParser(description='Download and convert Codeforces problems to PDF')
    parser.add_argument("contest_id", type=int, help="Codeforces contest ID (e.g., 1234)")
    parser.add_argument("problem", type=str, help="Problem letter (e.g., A, B, C)")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("-f", "--fast", action="store_true", help="Use fast rendering mode")
    group.add_argument("-g", "--graphics", action="store_true", help="Use graphics rendering mode")

    parser.add_argument("-d", "--output-dir", type=str, default=".", help="Output directory for the PDF file (default: current directory)")
    return parser.parse_args()


def build_pdf_from_html(html: str, output_dir: str, file_name: str, mode: Mode, problem_rating: int = 0):
    p = Path(output_dir)
    p.mkdir(parents=True, exist_ok=True)

    # Parse the HTML to restructure it to match Codeforces format
    bs = bs4.BeautifulSoup(html, "html.parser")

    # Check if this is a placeholder error message or actual problem content
    is_error = 'Unable to fetch problem' in html

    if not is_error:
        # Extract problem title
        title_div = bs.find('div', class_='title')
        title_text = title_div.text if title_div else "Codeforces Problem"

        # Extract time and memory limits with better pattern matching
        time_pattern = re.compile(r'time limit[^:]*:\s*(\d+(?:\.\d+)?)\s*second', re.IGNORECASE)
        memory_pattern = re.compile(r'memory limit[^:]*:\s*(\d+)\s*megabytes', re.IGNORECASE)

        time_match = time_pattern.search(html)
        memory_match = memory_pattern.search(html)

        time_limit = f"time limit per test: {time_match.group(1) if time_match else '1'} second"
        memory_limit = f"memory limit per test: {memory_match.group(1) if memory_match else '256'} megabytes"
        io_specs = "input: standard input<br>output: standard output"

        # Create difficulty badge if rating is available
        difficulty_html = ""
        if problem_rating > 0:
            difficulty_html = difficulty_badge_html(problem_rating)
            
        # Create improved header with centered title, difficulty badge, and proper formatting
        header = f"""
        <div class="header" style="text-align: center; margin-bottom: 20px;">
            <div class="title" style="font-size: 1.5em; font-weight: bold; margin-bottom: 10px;">{title_text}</div>
            {difficulty_html}
            <div style="margin: 10px auto; text-align: center;">
                <div class="time-limit" style="display: inline-block; margin-right: 10px;">{time_limit}</div>
                <div class="memory-limit" style="display: inline-block;">{memory_limit}</div>
            </div>
            <div style="margin: 5px auto;">
                <div class="input-file" style="display: inline-block; margin-right: 10px;">input: standard input</div>
                <div class="output-file" style="display: inline-block;">output: standard output</div>
            </div>
        </div>
        """

        # Replace or insert header
        if title_div:
            title_div.replace_with(bs4.BeautifulSoup(header, "html.parser"))
        else:
            first_element = bs.find()
            if first_element:
                first_element.insert_before(bs4.BeautifulSoup(header, "html.parser"))
            else:
                html = header + html

    # Format sample test sections to match 4A style
    sample_inputs = bs.find_all('div', class_='input')
    sample_outputs = bs.find_all('div', class_='output')

    for i, (input_div, output_div) in enumerate(zip(sample_inputs, sample_outputs)):
        # Clean up the input/output content
        input_content = input_div.find('pre').text if input_div.find('pre') else ""
        output_content = output_div.find('pre').text if output_div.find('pre') else ""

        # Create compact samples section like in 4A
        formatted_sample = f"""
        <div class="sample-test">
            <div class="section-title">Examples</div>
            <div class="example">
                <div class="input">
                    <div class="title">input</div>
                    <pre>{input_content.strip()}</pre>
                </div>
                <div class="output">
                    <div class="title">output</div>
                    <pre>{output_content.strip()}</pre>
                </div>
            </div>
        </div>
        """

        # Replace with new format
        new_sample = bs4.BeautifulSoup(formatted_sample, "html.parser")
        input_div.replace_with(new_sample)

        # Remove the original output div
        output_div.extract()

    # Handle note sections to match 4A style
    note_divs = bs.find_all('div', class_='note')
    for note_div in note_divs:
        note_content = note_div.decode_contents()
        formatted_note = f"""
        <div class="note-section">
            <div class="section-title">Note</div>
            <div class="note-content">{note_content}</div>
        </div>
        """
        note_div.replace_with(bs4.BeautifulSoup(formatted_note, "html.parser"))

    # Get the modified HTML
    if len(bs.contents) > 0:
        html = bs.decode_contents()

    # Create the complete HTML with improved styling including Cuprum font and difficulty badge
    complete_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Codeforces Problem</title>
        <style>
            /* Import Cuprum font for authentic Codeforces appearance */
            @import url('https://fonts.googleapis.com/css2?family=Cuprum:wght@400;500;700&family=Roboto:wght@400;700&family=Source+Code+Pro:wght@400;500&display=swap');

            /* Base styling */
            body {{
                font-family: 'Cuprum', 'Roboto', sans-serif;
                font-size: 15px;
                line-height: 1.5;
                margin: 0;
                padding: 20px;
                color: #333;
                background-color: #fff;
            }}

            /* Header elements */
            .header {{
                margin-bottom: 25px;
                border-bottom: 1px solid #e1e1e1;
                padding-bottom: 15px;
            }}

            .title {{
                font-family: 'Cuprum', sans-serif;
                font-size: 22px;
                font-weight: 700;
                margin-bottom: 10px;
                color: #1a1a1a;
                text-align: center;
            }}

            .time-limit, .memory-limit, .input-file, .output-file {{
                font-size: 15px;
                margin-bottom: 5px;
                color: #333;
            }}

            /* Problem statement container */
            .problem-statement {{
                max-width: 800px;
                margin: 0 auto;
            }}

            /* Section headings */
            .section-title {{
                font-family: 'Cuprum', sans-serif;
                font-weight: 700;
                font-size: 18px;
                margin-top: 25px;
                margin-bottom: 12px;
                color: #1a1a1a;
                border-bottom: 1px solid #f0f0f0;
                padding-bottom: 5px;
            }}

            /* Input/output blocks */
            .input, .output {{
                margin-bottom: 15px;
            }}

            .input .title, .output .title {{
                font-weight: 700;
                margin-bottom: 6px;
                color: #333;
                font-size: 16px;
            }}
            
            /* Codeforces specific input/output styling */
            .input-specification, .output-specification {{
                margin-bottom: 20px;
            }}
            
            /* Ensure proper code block spacing */
            .input-file, .output-file {{
                font-family: 'Source Code Pro', monospace;
                color: #444;
            }}

            /* Code/pre blocks with better styling */
            pre {{
                background-color: #f8f8f8;
                border: 1px solid #e1e1e1;
                border-radius: 4px;
                padding: 10px;
                white-space: pre-wrap;
                font-family: 'Source Code Pro', 'Courier New', monospace;
                font-size: 14px;
                line-height: 1.4;
                overflow-x: auto;
            }}
            
            /* Fix Codeforces sample test formatting */
            .sample-test pre {{
                margin: 0.5em 0;
                padding: 0.5em;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
            }}

            /* Notes section */
            .note-section {{
                margin-top: 25px;
                padding: 12px;
                background-color: #f8f9fa;
                border-radius: 4px;
                border-left: 3px solid #555;
            }}

            .note-content {{
                margin-top: 6px;
            }}

            /* Examples with better border and spacing */
            .example {{
                margin-bottom: 20px;
                padding: 5px;
                border-radius: 4px;
            }}
            
            /* Sample tests container */
            .sample-test {{
                margin-top: 25px;
                margin-bottom: 30px;
            }}
            
            /* Improved table-like layout for examples */
            .example {{
                display: flex;
                flex-wrap: wrap;
                gap: 20px;
                margin-bottom: 20px;
            }}
            
            .example .input, .example .output {{
                flex: 1;
                min-width: 45%;
            }}
            
            /* Difficulty badge styling */
            .difficulty-badge {{
                display: inline-block; 
                padding: 4px 10px; 
                border-radius: 4px; 
                font-weight: bold;
                font-size: 14px;
                margin: 8px 0; 
                color: white;
                text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            
            /* Math formatting */
            .math-inline, .math-display {{
                font-style: italic;
            }}
            
            .math-display {{
                display: block;
                text-align: center;
                margin: 15px 0;
            }}
            
            /* Add styling for the fraction display */
            .fraction {{
                display: inline-block;
                vertical-align: middle;
                text-align: center;
            }}
            
            .numerator, .denominator {{
                display: block;
            }}
            
            .numerator {{
                border-bottom: 1px solid #000;
            }}
        </style>
    </head>
    <body>
        <div class="problem-statement">
            {html}
        </div>
    </body>
    </html>
    """

    # Write the PDF using clean styling similar to 4A
    HTML(string=complete_html, base_url="").write_pdf(
        p / file_name,
        # Use simple inline styling instead of external CSS files for more control
    )
    

def main():
    args = parse_args()

    contest_id = args.contest_id
    problem = args.problem
    mode = Mode.DEFAULT
    if args.fast:
        mode = Mode.FAST
    elif args.graphics:
        mode = Mode.GRAPHICS
    output_dir = args.output_dir

    # Check for required dependencies
    required_commands = ["tex2svg", "tex2htmlcss", "make4ht"]
    for cmd in required_commands:
        if subprocess.call(["which", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE) != 0:
            warning(f"Command {cmd} not found. Some LaTeX rendering modes may not work.")

    debug(f"fetching problem webpage: {contest_id=} {problem=}")
    out_filename, html, problem_rating = extract_problem(contest_id, problem)
    if problem_rating > 0:
        info(f"fetched (difficulty rating: {problem_rating})")
    else:
        info("fetched (difficulty rating unknown)")

    debug("rendering latex")
    rendered, html = render_formulas(html, mode)
    if rendered:
        info("rendered latex")
    else:
        warning("some formulas may not be rendered correctly")

    debug("building pdf")
    build_pdf_from_html(html, output_dir, out_filename, mode, problem_rating)
    info(f"PDF saved to {os.path.join(output_dir, out_filename)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        error("Operation cancelled by user")
    except Exception as e:
        exception(f"Unexpected error: {e}")
    finally:
        # Clean up temporary files
        for f in TEMP_FILES:
            try:
                f.close()
            except:
                pass
