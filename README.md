# CodeForces2PDF

A professional tool for competitive programmers that converts Codeforces problems into elegantly formatted PDF documents, preserving original styling while enhancing readability.

## Overview

CodeForces2PDF bridges the gap between online problem statements and offline study materials. Whether you're preparing for a competition, teaching algorithms, or simply enjoy solving problems away from your computer, this tool creates publication-quality PDFs that maintain the essence of the original problems.

## Key Features

- **Intuitive Web Interface**: Thoughtfully designed with both novice and experienced users in mind
- **Flexible Input Options**: Work your way - enter contest and problem IDs or simply paste a URL
- **True-to-Original Styling**: Carefully crafted PDFs that respect Codeforces' layout and formatting
- **Mathematical Precision**: Properly rendered LaTeX formulas that preserve mathematical notation
- **Difficulty Indicators**: Visual cues that help you gauge problem complexity at a glance
- **Performance Focused**: Optimized for speed without sacrificing quality

## System Requirements

- Python 3.9 or newer
- Core dependencies (automatically installed):
  - Flask: Powers the responsive web interface
  - WeasyPrint: Handles the PDF conversion process
  - BeautifulSoup4: Manages HTML parsing with precision
  - httpx: Provides improved HTTP client capabilities
- Optional enhancements:
  - tex2svg: Improves formula rendering in default and graphics modes
  - make4ht: Enables faster rendering when speed is prioritized

## Getting Started

### Installation

1. Clone the repository to your local environment
   ```bash
   git clone https://github.com/yourusername/codeforces2pdf.git
   cd codeforces2pdf
   ```

2. Install required dependencies
   ```bash
   pip install -r requirements.txt
   ```

### Using the Web Interface

1. Launch the application server
   ```bash
   python main.py
   ```

2. Navigate to http://localhost:5000 in your preferred browser

3. Choose your preferred input method:
   - Enter the Contest ID and Problem letter separately
   - Paste a complete Codeforces problem URL
   - Preview your selection before committing to download

### Command Line Usage

For those who prefer terminal-based workflows:

```bash
python codeforces_to_pdf.py [options] <contest_id> <problem>
```

Available options:
- `-d, --dir`: Specify a custom output directory
- `-f, --fast`: Prioritize speed over formula rendering quality
- `-g, --graphics`: Generate high-quality SVG graphics for mathematical expressions

Example workflows:

```bash
# Download the classic "Watermelon" problem (4A)
python codeforces_to_pdf.py 4 A

# Quickly generate a PDF for problem C from contest 1000
python codeforces_to_pdf.py -f 1000 C

# Save a problem to a specific directory for your archives
python codeforces_to_pdf.py -d ./competition_prep 1234 B
```

## Recent Enhancements

We've made significant improvements based on user feedback:

- **Intelligent URL Processing**: The system now automatically extracts relevant details from pasted URLs
- **Refined Visual Styling**: Closer alignment with Codeforces' presentation, particularly for examples and code blocks
- **Typography Improvements**: Enhanced readability for both code and mathematical expressions
- **Example Presentation**: Better delineation of sample inputs and outputs for clearer understanding
- **Processing Efficiency**: Streamlined operations for faster problem retrieval and conversion

## PDF Design Philosophy

Each generated PDF follows careful design principles:

- **Typography**: Selected fonts that balance readability with professional appearance
- **Layout**: Thoughtful spacing that reduces eye strain during extended reading
- **Emphasis**: Appropriate highlighting for important elements like constraints and specifications
- **Consistency**: Uniform presentation of similar elements across different problems
- **Accessibility**: High contrast and clear structure to improve readability

## Community and Use Cases

CodeForces2PDF serves diverse needs within the competitive programming community:

- **Individual Competitors**: Practice offline without distractions or internet connectivity
- **Educators**: Create printed problem sets for classroom exercises and examinations
- **Study Groups**: Compile collections of thematically related problems for focused practice
- **Algorithm Enthusiasts**: Build personalized archives of interesting problems for reference

## Contributing

Your expertise can help make this tool even better. We welcome contributions of all kinds:

1. Fork the repository to your GitHub account
2. Create a focused feature branch (`git checkout -b feature/new-capability`)
3. Implement your improvement with appropriate documentation
4. Submit a well-described pull request for review

## License

This project is available under the MIT License, allowing for both personal and commercial use with proper attribution.

## Acknowledgments

- Original concept inspired by [@AliOsm](https://github.com/AliOsm/)  |  [AliOsm/codeforces2pdf](https://github.com/AliOsm/codeforces2pdf)
- Built with appreciation for the competitive programming community and Codeforces platform
