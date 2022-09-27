#! /usr/bin/env python3

import zipfile
import sys
import os
import shutil
import urllib.parse
import regex
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

temp_unzip = ""
tocitems = []
spineitems = []
accumulator = ""
make_csv = False

# there may be a one to many relationship between TocItem and SpineItem

class TocItem():
    title = ""
    href = ""
    word_count = 0


class SpineItem():
    href = ""
    spine_id = ""
    word_count = 0


def clear_output():
    global accumulator
    accumulator = ""


def collect_output(to_write:str):
    global accumulator
    accumulator += to_write + "\n"


def write_output(fpath: str):
    with open(fpath, "w") as outfile:
        outfile.write(accumulator)


def href_to_filepath(href: str) -> str:
    temp = urllib.parse.unquote(href)  # get rid of %20 etc
    bits = temp.split('/')
    path = ""
    for bit in bits:
        path = os.path.join(path, bit)
    return path


def process_toc_ncx(tocfile:str):
    # this is an xml file, a bit messy to parse
    global tocitems
    tree = ET.parse(tocfile)
    root = tree.getroot()
    tocitems = []
    navMap = None

    for child in root:
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
                tocitem.href = child.get("src","-")
                if "#" in tocitem.href:
                    bits = tocitem.href.split("#")
                    tocitem.href = bits[0]
                tocitem.href = href_to_filepath(tocitem.href)
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
                tocitem.href = match.group(1)
                if "#" in tocitem.href:
                    bits = tocitem.href.split("#")
                    tocitem.href = bits[0]
                tocitem.href = href_to_filepath(tocitem.href)
                tocitems.append(tocitem)
        tf.close()


def process_content_opf(opffile:str):
    # this should only be called if we can't find toc
    global tocitems
    # read_spine(opffile)  # spine should already have been read
    for spineitem in spineitems:
        tocitem = TocItem()
        temp = regex.sub(r'\.x?html', '', spineitem.href)
        tocitem.title = regex.sub(r'[\-_]', ' ', temp).strip()
        tocitem.href = spineitem.href
        tocitem.href = href_to_filepath(tocitem.href)
        tocitems.append(tocitem)


def count_words(html_file) -> int:
    total_words = 0
    if os.path.exists(html_file):
        with open(html_file,"r") as hf:
            html = hf.read()
            hf.close()

        # we use the "BeautifulSoup" package which is an easy way to parse a HTML file    
        soup = BeautifulSoup(html, "html.parser")
        resultSet = soup.find_all(["h","p"])  # find all headings and paragraphs
        for result in resultSet:
            strings = result.stripped_strings
            for text in strings:
                if text:
                    bits = text.split(" ")
                    total_words += len(bits)
    return total_words


def read_spine(opffile:str):
    global spineitems
    spineitems = []
    manifest_items = []
    with open(opffile, "r") as opf:
        lines = opf.readlines()
        # first, have to read the manifest, which has the correct URLs
        # manifest is not in same order as the spine! Need it in spine order
        item_pattern = r'<item '
        href_pattern = r'href="(.*?)"'
        id_pattern = r'id="(.*?)"'
        for line in lines:
            match_item = regex.search(item_pattern, line)
            if match_item:
                match_href = regex.search(href_pattern, line)
                if match_href:
                    manifest_item = SpineItem()
                    manifest_item.href = match_href.group(1)
                    match_id = regex.search(id_pattern, line)
                    if match_id:
                        manifest_item.spine_id = match_id.group(1)

                    manifest_items.append(manifest_item)
        href_pattern = r'idref="(.*?)"'
        for line in lines:
            match_href = regex.search(href_pattern, line)
            if match_href:
                spineitem = SpineItem()
                spineitem.spine_id = match_href.group(1)
                spineitems.append(spineitem)

        for spineitem in spineitems:
            for manifest_item in manifest_items:
                if manifest_item.spine_id == spineitem.spine_id:
                    spineitem.href = manifest_item.href
                    if "#" in spineitem.href:
                        bits = spineitem.href.split("#")
                        spineitem.href = bits[0]
                    spineitem.href = href_to_filepath(spineitem.href)
                    break
            if not spineitem.href:
                spineitems.remove(spineitem)
                    
        opf.close()

        head, _ = os.path.split(opffile)
        for spineitem in spineitems:
            if not spineitem.href:
                print("Error! empty href")
                spineitem.word_count = -1
            else:
                spineitem.word_count = count_words(os.path.join(head,spineitem.href))


def recursive_find(wanted:str, root_path: str) -> str:
    return_val = None
    for root, dirs, files in os.walk(root_path, topdown=True):
        for afile in files:
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


def get_tocitem_for_spine(spineitem:SpineItem) -> TocItem:
    tocitem: TocItem = None
    for tocitem in tocitems:
        if tocitem.href == spineitem.href:
            return tocitem
    return None


def allocate_count_to_tocitems(bookname: str):
    global tocitems, spineitems
    spineitem: SpineItem = None
    bookToC = TocItem()
    bookToC.title = bookname
    lastToC = bookToC
    for spineitem in spineitems:
        tocitem = get_tocitem_for_spine(spineitem)
        if tocitem:
            lastToC = tocitem
        else:
            tocitem = lastToC
        tocitem.word_count += spineitem.word_count


def output_results(bookname):
    for tocitem in tocitems:
        if make_csv:
            collect_output(f'"{bookname}","{tocitem.title}",{tocitem.word_count}')
        else:
            collect_output(f"{tocitem.title}: {tocitem.word_count} words")


def process_epub(epub_folder: str, path_to_file:str, bookname: str):
    global tocitems, spineitems

    # we start by unpacking the epub (which is just a zip file)
    create_unzip_folder(epub_folder)
    with zipfile.ZipFile(path_to_file, 'r') as zip_ref:
        zip_ref.extractall(temp_unzip)

    tocitems = []
    spineitems = []
    print(f"Starting to process {bookname}")

    opf_file = get_content_opf_file()  # may return None
    if not opf_file:
        print("unable to find content.opf")
        exit(-1)
    
    read_spine(opf_file)  # this also counts words in each spine item

    # now try to find toc in various ways
    toc_path = recursive_find("toc.ncx", temp_unzip)
    if toc_path:
        process_toc_ncx(toc_path)
        allocate_count_to_tocitems(bookname)
        return

    toc_path = recursive_find("toc.html", temp_unzip)
    if not toc_path:
        toc_path = recursive_find("toc.xhtml", temp_unzip)
    if toc_path:
        process_toc_html(toc_path)
        allocate_count_to_tocitems(bookname)
        return

    # this is desperation, no toc.ncx or toc.xhtml, so build tocitems based on spine only
    spineitem:SpineItem = None
    for spineitem in spineitems:
        tocitem = TocItem()
        tocitem.title = regex.sub(r'[-_]',' ',spineitem.spine_id)
        tocitem.title = regex.sub(r'\.x?html','',tocitem.title)
        tocitem.href = spineitem.href
        tocitems.append(tocitem)
    allocate_count_to_tocitems(bookname)


def process_tocitems(filepath: str, bookname:str, read_title: bool = False):
    head, _ = os.path.split(filepath)
    tocitem = TocItem()
    for tocitem in tocitems:
        # get rid of any anchors in the src URL
        if "#" in tocitem.href:
            bits = tocitem.href.split("#")
            tocitem.href = bits[0]

        if not tocitem.href.endswith("html"):
            continue  # only want to process content files

        html_file = os.path.join(head, tocitem.href)
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
                output_results(bookname)
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
