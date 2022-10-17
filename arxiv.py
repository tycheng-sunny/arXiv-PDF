import os
import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from fpdf import FPDF
import datetime

date = datetime.datetime.now().strftime("%a_%d%b%y")
options = Options()
options.add_argument("--headless")
driver = webdriver.Chrome("/usr/local/chromedriver", options=options)

title = []
_url = []
author_list = []
abstract = []
home = os.path.expanduser('~')
outpath = home + "/Desktop/arXivPDF/"
if not os.path.exists(outpath):
    os.mkdir(outpath)
webpath = "https://arxiv.org"
driver.get("https://arxiv.org/list/astro-ph.GA/recent")
content = driver.page_source
soup = BeautifulSoup(content)
#driver.close()
#print(soup)
for a in soup.find_all("a", title="Abstract"):
    abslink = str(webpath + a['href'])
    driver.get(abslink)
    _ = driver.page_source
    _soup = BeautifulSoup(_)
    author_count = 0 # list up to 5 authors
    #print(abslink)
    _url.append(abslink)
    for b in _soup.find_all("meta", attrs={"name":"citation_title"}):
        title.append(str(b["content"]))
    for b in _soup.find_all("meta", attrs={"name":"citation_abstract"}):
        abs = ""
        for word in b["content"].split():
            abs += word + ' '
        abs = abs[:-1]
        abstract.append(abs)
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

# create a cell
for a in range(len(_url)):
    pdf.cell(190, 10, txt = ('[%s]  ' % str(a) + str(_url[a])), link=_url[a], ln=1)
    pdf.set_font("Arial", style="B", size = 14)
    #pdf.write(10, txt="Title = ")
    pdf.write(5, txt = (title[a]))
    pdf.ln(7)
    pdf.set_font("Arial", style="U", size = 14)
    pdf.write(5, txt = (author_list[a]))
    pdf.ln(7)
    pdf.set_font("Arial", style="B", size = 14)
    pdf.write(6, txt = "Abstract = ")
    pdf.ln(7)
    pdf.set_font("Arial", size = 14)
    #pdf.write(6, txt = abstract[a])#, align='C')
    pdf.multi_cell(190, 5, txt = abstract[a], align='J')
    pdf.ln(15)
pdf.output(outpath + "arXiv_" + date + ".pdf")
