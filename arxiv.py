import os
import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from fpdf import FPDF
import datetime
from PIL import Image

date = datetime.datetime.now().strftime("%d%b%y")
options = Options()
options.add_argument("--headless")
#options.add_argument(f"--force-device-scale-factor={1.}")
driver = webdriver.Chrome("/usr/local/chromedriver", options=options)

# extracted information
title = []
_url = []
author_list = []
abstract = []
home = os.path.expanduser('~') # read the path of HOME directory
outpath = home + "/Desktop/arXivPDF/" # output directory. Default: create a new directory at /Desktop
if not os.path.exists(outpath):
    os.mkdir(outpath)
webpath = "https://arxiv.org"
driver.get("https://arxiv.org/list/astro-ph.GA/recent") # use Google Chrome to open this web
content = driver.page_source # read source code
soup = BeautifulSoup(content)
for ind, a in enumerate(soup.find_all("a", title="Abstract")):
    abslink = str(webpath + a['href']) # link to the abstract page of a paper
    ## redirect website to the abstract page of a paper
    driver.get(abslink)
    
    driver.maximize_window()
    width = driver.execute_script("return Math.max( document.body.scrollWidth, document.body.offsetWidth, document.documentElement.clientWidth, document.documentElement.scrollWidth, document.documentElement.offsetWidth );")
    height = driver.execute_script("return Math.max( document.body.scrollHeight, document.body.offsetHeight, document.documentElement.clientHeight, document.documentElement.scrollHeight, document.documentElement.offsetHeight );")

    # Set the window size to match the entire webpage
    driver.set_window_size(width, height)

    screensh = driver.find_element(By.TAG_NAME, 'blockquote')
    screensh.screenshot((outpath+"screenshot_ab%d.png" %ind))
    
    _ = driver.page_source
    _soup = BeautifulSoup(_)
    author_count = 0 # list up to 5 authors
    ## collect information of all new papers
    _url.append(abslink)
    for b in _soup.find_all("meta", attrs={"name":"citation_title"}):
        title.append(str(b["content"]))
    '''
    for b in _soup.find_all("meta", attrs={"name":"citation_abstract"}):
        print(b)
        abs = ""
        for word in b["content"].split():
            abs += word + ' '
        abs = abs[:-1]
        abstract.append(abs)
    '''
    for b in _soup.find_all("meta", attrs={"name":"citation_author"}):
        if author_count < 5:
            if author_count == 0:
                authors = str(b["content"])
            else:
                authors += ('; '+str(b["content"]))
        author_count += 1
    author_list.append(authors)
driver.close()

# output PDF file
pdf = FPDF()
# Add a page
pdf.add_page()
# set style and size of font
# that you want in the pdf
pdf.add_font("Arial", "", "arial/arial.ttf", uni=True)
pdf.set_font("Arial", size = 14)
#construct a document
for a in range(len(_url)):
    pdf.cell(190, 10, txt = ('[%s]  ' % str(a+1) + str(_url[a])), link=_url[a], ln=1)
    pdf.set_font("Arial", style="B", size = 14)
    #pdf.write(10, txt="Title = ")
    pdf.write(5, txt = (title[a]))
    pdf.ln(7)
    pdf.set_font("Arial", style="U", size = 14)
    pdf.write(5, txt = (author_list[a]))
    pdf.ln(7)
    pdf.image((outpath+"screenshot_ab%d.png" %a))
    os.remove((outpath+"screenshot_ab%d.png" %a))
    #pdf.set_font("Arial", style="B", size = 14)
    #pdf.write(6, txt = "Abstract = ")
    #pdf.ln(7)
    #pdf.set_font("Arial", size = 14)
    #pdf.write(6, txt = abstract[a])#, align='C')
    #pdf.multi_cell(190, 5, txt = abstract[a], align='J')
    #pdf.ln(15)
    if a < (len(_url)-1):
        pdf.add_page()
pdf.output(outpath + "arXiv_" + date + ".pdf")
