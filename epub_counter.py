#! /usr/bin/env python3

import zipfile
import sys
import os
import shutil
import regex
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

temp_unzip = ""
tocitems = []
accumulator = ""
make_csv = False

class TocItem():
    title = ""
    src = ""
    wordcount = 0


class SpineItem():
    href = ""
    spine_id = ""


def clear_output():
    global accumulator
    accumulator = ""


def collect_output(to_write:str):
    global accumulator
    accumulator += to_write + "\n"


def write_output(fpath: str):
    with open(fpath, "w") as outfile:
        outfile.write(accumulator)


def process_toc_ncx(tocfile:str):
    # this is an xml file, a bit messy to parse
    global tocitems
    tree = ET.parse(tocfile)
    root = tree.getroot()
    tocitems = []
    navMap = None

    for child in root:
        # print(child.tag)
        if "navMap" in child.tag:
            navMap = child
            continue

    if not navMap:
        print("Error, no navMap found")
        return

    for navPoint in navMap:
        tocitem = TocItem()
        for child in navPoint:
            if "navLabel" in child.tag:
                tocitem.title = "".join(child.itertext()).strip()
            if "content" in child.tag:
                tocitem.src = child.get("src","-")
        tocitems.append(tocitem)


def process_toc_html(tocfile:str):
    global tocitems
    with open(tocfile, "r") as tf:
        lines = tf.readlines()
        pattern = r'<a href="(.*?)">(.*?)</a>'
        for line in lines:
            match = regex.search(pattern, line)
            if match:
                tocitem = TocItem()
                tocitem.title = match.group(2).strip()
                tocitem.src = match.group(1)
                tocitems.append(tocitem)
        tf.close()


def process_content_opf(opffile:str):
    global tocitems
    read_spine(opffile)
    for spineitem in spineitems:
        tocitem = TocItem()
        temp = regex.sub(r'\.x?html', '', spineitem.href)
        tocitem.title = regex.sub(r'[\-_]', ' ', temp).strip()
        tocitem.src = spineitem.href
        tocitems.append(tocitem)


def read_spine(opffile:str):
    global spineitems
    spineitems = []
    manifest_items = []
    with open(opffile, "r") as opf:
        lines = opf.readlines()
        # first, have to read the manifest, which has the correct URLs
        # manifest is not in same order as the spine! Need it in spine order
        pattern = r'<item href="(.*?)" id="(.*?)"'
        for line in lines:
            match = regex.search(pattern, line)
            if match:
                manifest_item = SpineItem()
                manifest_item.href = match.group(1)
                manifest_item.spine_id = match.group(2)
                manifest_items.append(manifest_item)
        pattern = r'<itemref idref="(.*?)"'
        for line in lines:
            match = regex.search(pattern, line)
            if match:
                spineitem = SpineItem()
                spineitem.spine_id = match.group(1)
                spineitems.append(spineitem)
        for spineitem in spineitems:
            for manifest_item in manifest_items:
                if manifest_item.spine_id == spineitem.spine_id:
                    spineitem.href = manifest_item.href
        opf.close()


def recursive_find(wanted:str, root_path: str) -> str:
    return_val = None
    for root, dirs, files in os.walk(root_path, topdown=True):
        for afile in files:
            # print(os.path.join(root, afile))
            if wanted in afile:
                return os.path.join(root, afile)
        for folder in dirs:
            return_val = recursive_find(wanted=wanted, root_path=os.path.join(root, folder))
            if return_val:
                return return_val
    return return_val


def get_content_opf_file() -> str:
    opf_file = recursive_find(".opf", temp_unzip)  # might be called content.opf or package.opf or whatever.
    return opf_file


def process_epub(epub_folder: str, path_to_file:str, bookname: str):
    global tocitems

    # we start by unpacking the epub (which is just a zip file)
    create_unzip_folder(epub_folder)
    with zipfile.ZipFile(path_to_file, 'r') as zip_ref:
        zip_ref.extractall(temp_unzip)

    opf_file = get_content_opf_file()  # may return None

    # now try to find toc in various ways
    toc_path = recursive_find("toc.ncx", temp_unzip)
    if toc_path:
        process_toc_ncx(toc_path)
        process_tocitems(toc_path, bookname=bookname)
        return

    toc_path = recursive_find("toc.html", temp_unzip)
    if not toc_path:
        toc_path = recursive_find("toc.xhtml", temp_unzip)
    if toc_path:
        process_toc_html(toc_path)
        process_tocitems(toc_path, bookname=bookname)
        return

    # this is desperation, no toc.ncx or toc.xhtml, so read spine then try to find titles
    if not opf_file:
        print("Couldn't find content.opf")
        exit(-1)

    toc_path = opf_file    
    process_content_opf(opf_file)
    process_tocitems(toc_path, bookname=bookname, read_title=True)
    return


def process_tocitems(filepath: str, bookname:str, read_title: bool = False):
    head, _ = os.path.split(filepath)
    tocitem = TocItem()
    for tocitem in tocitems:
        # get rid of any anchors in the src URL
        if "#" in tocitem.src:
            bits = tocitem.src.split("#")
            tocitem.src = bits[0]

        if not tocitem.src.endswith("html"):
            continue  # only want to process content files

        html_file = os.path.join(head, tocitem.src)
        if os.path.exists(html_file):
            with open(html_file,"r") as hf:
                html = hf.read()
                hf.close()

            # we use the "BeautifulSoup" package which is an easy way to parse a HTML file    
            soup = BeautifulSoup(html, "html.parser")
            if read_title:
                title_tag = soup.find("title")
                if title_tag.string:
                    tocitem.title = title_tag.string

            resultSet = soup.find_all(["h","p"])  # find all headings and paragraphs
            total_words = 0
            for result in resultSet:
                strings = result.stripped_strings
                for text in strings:
                    if text:
                        bits = text.split(" ")
                        total_words += len(bits)
            tocitem.wordcount = total_words
            tocitem.title = tocitem.title.strip()
        if make_csv:
            collect_output(f'"{bookname}","{tocitem.title}",{tocitem.wordcount}')
        else:
            collect_output(f"{tocitem.title}: {tocitem.wordcount} words")
        

def create_unzip_folder(epub_folder: str):
    global temp_unzip
    temp_unzip = os.path.join(epub_folder,"unzipped")
    if not os.path.exists(temp_unzip):
        os.mkdir(temp_unzip)
    else:
        remove_unzip_folder()
        os.mkdir(temp_unzip)


def remove_unzip_folder():
    global temp_unzip
    if os.path.exists(temp_unzip):
        try:
            shutil.rmtree(temp_unzip)
        except OSError as e:
            print("Error: %s : %s" % (temp_unzip, e.strerror))


def main() -> None:
    global make_csv

    # directory of epub files must be passed as first argument on command line
    if len(sys.argv) < 2:
        print("""USAGE: epub_counter DIRECTORY [-c]
        where DIRECTORY is a directory of the epubs we want to process
        and -c optional output as CSV file""")
        exit(0)

    epub_folder = sys.argv[1]

    # check to see if CSV output is wanted and if so, set flag
    if len(sys.argv) > 2:
        if sys.argv[2].lower() == "-c":
            make_csv = True
            # write field names for CSV
            collect_output(f'"Book","Title","Words"')

    if os.path.exists(epub_folder):
        # cycle through each file in the folder and process if it's an epub.
        for afile in os.listdir(epub_folder):
            if afile.endswith(".epub"):
                _, tail = os.path.split(afile)
                bookname = regex.sub(r'.epub','',tail)
                if not make_csv:
                    collect_output(f"\n\nprocessing {afile}")
                path = os.path.join(epub_folder, afile)
                process_epub(epub_folder, path, bookname)
        if make_csv:
            write_output(os.path.join(epub_folder,"results.csv"))
        else:
            write_output(os.path.join(epub_folder,"results.txt"))            
        remove_unzip_folder()
    else:
        print("ERROR: No such directory!")
        exit(-1)


if __name__ == "__main__":
    main()
