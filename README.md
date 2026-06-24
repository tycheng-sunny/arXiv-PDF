# arXiv-PDF
This code extracts (1) title, (2) authors (up to 5), (3) abstract, (4) arXiv link from arXiv website, and output a PDF file.

## Requirements
- This code uses **chromedriver** to open arXiv website in code. Please download from [here](https://chromedriver.chromium.org) and install it.
- Python package: arxiv==2.3.2, reportlab, pylatexenc, matplotlib

- In the code, one can tune everything in the CONFIG block for choosing different arXiv categories, different max numbers. 
