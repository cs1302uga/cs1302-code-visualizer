#!/usr/bin/env python3

import os
from pathlib import Path
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import fileinput

this_files_dir = Path(os.path.realpath(os.path.dirname(__file__)))


def main():
    stdin_data = "".join(fileinput.input())

    frontend_path = (this_files_dir / "frontend" / "iframe-embed.html").as_uri()
    frontend_query = f"?data={quote(stdin_data)}"

    options = Options()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(2)  # only wait 2 secods for element to show up
    driver.get(frontend_path + frontend_query)
    # zoom borks screenshot, see https://stackoverflow.com/questions/39600245/how-to-capture-website-screenshot-in-high-resolution
    # driver.execute_script("document.body.style.zoom='150%'")
    driver.find_element(By.ID, "dataViz").screenshot("/home/ggliv/test.png")
    driver.quit()


if __name__ == "__main__":
    main()
