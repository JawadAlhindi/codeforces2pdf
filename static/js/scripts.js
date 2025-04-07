document.addEventListener('DOMContentLoaded', function() {
    console.log("Scripts loaded");
    
    const contestIdInput = document.getElementById('contest_id');
    const problemInput = document.getElementById('problem');
    const modeSelect = document.getElementById('mode');
    const previewBtn = document.getElementById('preview-btn');
    const downloadBtn = document.getElementById('download-btn');
    const problemPreview = document.getElementById('problem-preview');
    const problemUrlInput = document.getElementById('problem_url');
    const convertForm = document.getElementById('convert-form');
    
    // Form hidden fields
    const formContestId = document.getElementById('form_contest_id');
    const formProblem = document.getElementById('form_problem');
    const formMode = document.getElementById('form_mode');
    
    // Preview elements
    const previewTitle = document.getElementById('preview-title');
    const previewBadge = document.getElementById('preview-badge');
    const previewTime = document.getElementById('preview-time');
    const previewMemory = document.getElementById('preview-memory');
    const previewLoading = document.getElementById('preview-loading');
    const previewContent = document.getElementById('preview-content');
    const previewError = document.getElementById('preview-error');
    
    console.log("Preview button:", previewBtn);
    
    // Generate a badge HTML for a difficulty rating
    function getDifficultyBadge(rating) {
        let color = "#808080"; // Default gray
        if (rating === 0) {
            return `<span class="badge-difficulty" style="background-color: ${color};">Unknown</span>`;
        } else if (rating < 1200) {
            color = "#3db73d"; // Green
        } else if (rating < 1400) {
            color = "#00c0c0"; // Cyan
        } else if (rating < 1600) {
            color = "#0000ff"; // Blue
        } else if (rating < 1900) {
            color = "#aa00aa"; // Violet
        } else if (rating < 2100) {
            color = "#ff8c00"; // Orange
        } else if (rating < 2400) {
            color = "#ff0000"; // Red
        } else {
            color = "#aa0000"; // Dark red
        }
        return `<span class="badge-difficulty" style="background-color: ${color};">Difficulty: ${rating}</span>`;
    }
    
    // Parse problem URL to fill contest ID and problem ID
    if (problemUrlInput) {
        problemUrlInput.addEventListener('input', function() {
            const url = this.value.trim();
            if (!url) return;
            
            // Parse Codeforces URLs
            // Examples:
            // https://codeforces.com/contest/1234/problem/A
            // https://codeforces.com/problemset/problem/1234/A
            // https://codeforces.com/gym/1234/problem/A
            
            const regexPatterns = [
                /codeforces\.com\/contest\/(\d+)\/problem\/([A-Za-z0-9]+)/,
                /codeforces\.com\/problemset\/problem\/(\d+)\/([A-Za-z0-9]+)/,
                /codeforces\.com\/gym\/(\d+)\/problem\/([A-Za-z0-9]+)/
            ];
            
            for (const pattern of regexPatterns) {
                const match = url.match(pattern);
                if (match) {
                    contestIdInput.value = match[1];
                    problemInput.value = match[2];
                    
                    // Auto-trigger the preview
                    setTimeout(() => {
                        previewBtn.click();
                    }, 500);
                    
                    break;
                }
            }
        });
    }
    
    // Additional handler for when URL is pasted and form is submitted directly
    if (convertForm) {
        convertForm.addEventListener('submit', function(e) {
            if (problemUrlInput && problemUrlInput.value.trim() && 
                (!contestIdInput.value || !problemInput.value)) {
                e.preventDefault();
                alert('Please wait while the URL is processed');
                
                // Try to parse the URL here as well for immediate action
                const url = problemUrlInput.value.trim();
                const regexPatterns = [
                    /codeforces\.com\/contest\/(\d+)\/problem\/([A-Za-z0-9]+)/,
                    /codeforces\.com\/problemset\/problem\/(\d+)\/([A-Za-z0-9]+)/,
                    /codeforces\.com\/gym\/(\d+)\/problem\/([A-Za-z0-9]+)/
                ];
                
                for (const pattern of regexPatterns) {
                    const match = url.match(pattern);
                    if (match) {
                        contestIdInput.value = match[1];
                        problemInput.value = match[2];
                        
                        // Trigger preview then submit form
                        setTimeout(() => {
                            previewBtn.click();
                            // Wait for preview to load before submitting
                            setTimeout(() => {
                                convertForm.submit();
                            }, 1500);
                        }, 500);
                        
                        break;
                    }
                }
            }
        });
    }
    
    // Handle preview button click
    if (previewBtn) {
        previewBtn.addEventListener('click', function() {
            console.log("Preview button clicked");
            const contestId = contestIdInput.value.trim();
            const problem = problemInput.value.trim().toUpperCase();
            const mode = modeSelect.value;
            
            if (!contestId || !problem) {
                alert('Please enter both Contest ID and Problem ID');
                return;
            }
            
            // Show problem preview section with loading state
            problemPreview.style.display = 'block';
            previewLoading.classList.remove('d-none');
            previewContent.classList.add('d-none');
            previewError.classList.add('d-none');
            
            console.log("Fetching problem details for:", contestId, problem);
            
            // Make API request to check problem availability and get details
            fetch('/check-availability', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    contest_id: contestId,
                    problem: problem
                }),
            })
            .then(response => {
                console.log("Response received:", response);
                return response.json();
            })
            .then(data => {
                console.log("Data received:", data);
                previewLoading.classList.add('d-none');
                
                if (data.success) {
                    // Show problem details
                    previewContent.classList.remove('d-none');
                    previewTitle.textContent = data.title || `Problem ${contestId}${problem}`;
                    
                    // Update time and memory limits if available
                    if (data.time_limit) {
                        previewTime.textContent = `time limit: ${data.time_limit}`;
                    }
                    if (data.memory_limit) {
                        previewMemory.textContent = `memory limit: ${data.memory_limit}`;
                    }
                    
                    // Display difficulty badge if available
                    if (data.rating) {
                        previewBadge.innerHTML = getDifficultyBadge(data.rating);
                    } else {
                        previewBadge.innerHTML = getDifficultyBadge(0);
                    }
                    
                    // Enable download button
                    downloadBtn.disabled = false;
                    
                    // Set form values
                    formContestId.value = contestId;
                    formProblem.value = problem;
                    formMode.value = mode;
                    
                } else {
                    // Show error
                    previewError.classList.remove('d-none');
                    downloadBtn.disabled = true;
                }
            })
            .catch(error => {
                console.error('Error:', error);
                previewLoading.classList.add('d-none');
                previewError.classList.remove('d-none');
                downloadBtn.disabled = true;
            });
        });
    } else {
        console.error("Preview button not found in the DOM");
    }
});
