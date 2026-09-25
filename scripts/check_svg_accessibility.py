"""Verify SVG selection, clipboard copying and gallery disclosure keyboard behavior."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from cs1302_code_visualizer.browser_driver import get_webdriver


def check_gallery(output: Path, browser: str) -> dict:
    """Exercise browser input, saving only clipboard text copied by this check."""
    if browser == "firefox":
        options = webdriver.FirefoxOptions()
        options.add_argument("-headless")
        driver = webdriver.Firefox(options=options)
    else:
        driver = get_webdriver()
    modifier = Keys.COMMAND if sys.platform == "darwin" else Keys.CONTROL
    results = {}
    try:
        driver.set_window_size(1500, 1100)
        for mode, file in [("gallery", "index.html"), ("standalone", "edges.svg")]:
            # Start with a known clipboard value; never inspect the user's clipboard.
            driver.get("data:text/html,<textarea autofocus>svg-copy-check</textarea>")
            box = driver.find_element(By.CSS_SELECTOR, "textarea")
            box.click()
            ActionChains(driver).key_down(modifier).send_keys("a").send_keys("c").key_up(
                modifier
            ).perform()
            driver.get((output / file).resolve().as_uri())
            if mode == "gallery":
                disclosure = driver.find_element(By.CSS_SELECTOR, "#example0 .description summary")
                driver.execute_script("arguments[0].focus()", disclosure)
                disclosure.send_keys(Keys.SPACE)
                assert driver.execute_script("return arguments[0].parentElement.open", disclosure)
                driver.save_screenshot(str(output / f"{browser}-description.png"))
                disclosure.send_keys(Keys.TAB)
                assert driver.switch_to.active_element.text == "Reproduce this comparison"
                # Multiple SVGs must not share IDs or leave local references unresolved.
                assert driver.execute_script(r"""
                    const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
                    const references = [...document.querySelectorAll('svg *')].flatMap(e =>
                          [...e.attributes].flatMap(a => [...a.value.matchAll(/url\(#([^)]+)\)/g)].map(m => m[1])));
                        return ids.length === new Set(ids).size && references.every(id => document.getElementById(id));
                """)
                prefix = "#edges "
            else:
                prefix = ""
            if browser == "chrome":
                nodes = driver.execute_cdp_cmd("Accessibility.getFullAXTree", {})["nodes"]
                images = [
                    n
                    for n in nodes
                    if n.get("role", {}).get("value") == "image"
                    and n.get("name", {}).get("value", "").startswith("Java program memory state")
                ]
                assert images
                if mode == "standalone":
                    assert "reference to object" in images[0]["description"]["value"]
                else:
                    assert all(not n.get("description", {}).get("value") for n in images)
                results[mode + "_accessible_images"] = [
                    {key: n[key]["value"] for key in ("name", "description") if key in n}
                    for n in images
                ]
            target = next(
                t
                for t in driver.find_elements(By.CSS_SELECTOR, prefix + "svg text")
                if "café" in t.text
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'})", target)
            ActionChains(driver).double_click(target).perform()
            assert driver.execute_script("return getSelection().toString().length > 0")
            # Copy a full text element as well, to check whitespace, escaping and Unicode.
            expected = driver.execute_script(
                """
                const range = document.createRange(); range.selectNodeContents(arguments[0]);
                getSelection().removeAllRanges(); getSelection().addRange(range);
                return getSelection().toString();
            """,
                target,
            )
            assert "café" in expected and "👩‍💻" in expected
            ActionChains(driver).key_down(modifier).send_keys("c").key_up(modifier).perform()
            driver.save_screenshot(str(output / f"{browser}-{mode}-selection.png"))
            driver.get("data:text/html,<textarea autofocus></textarea>")
            box = driver.find_element(By.CSS_SELECTOR, "textarea")
            box.click()
            ActionChains(driver).key_down(modifier).send_keys("v").key_up(modifier).perform()
            # Chrome converts layout nonbreaking spaces to ordinary spaces on copy.
            assert box.get_attribute("value") == expected.replace("\u00a0", " "), (
                f"{browser} {mode}: copied text differs"
            )
            results[mode] = {
                "mouse_selection": "passed",
                "clipboard_roundtrip": "passed",
                "copied_text": box.get_attribute("value"),
            }
        results["browser"] = driver.capabilities.get("browserVersion")
        results["keyboard_disclosure"] = "passed"
        results["voiceover_safari"] = "Pending manual verification"
    finally:
        driver.quit()
    (output / f"{browser}-accessibility.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )
    return results


def main() -> None:
    """Run checks against a generated gallery containing example0 and edges."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gallery", type=Path)
    parser.add_argument("--browser", choices=["chrome", "firefox"], default="chrome")
    args = parser.parse_args()
    print(json.dumps(check_gallery(args.gallery, args.browser), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
