from util.clean_html import clean_html_for_llm


def test_clean_html():
    with open("test_html_outputs/qvc_com_raw.html", "r") as f:
        html = f.read()
    cleaned_html = clean_html_for_llm(html)
    with open("test_html_outputs/qvc_com_cleaned.html", "w") as f:
        f.write(cleaned_html)


test_clean_html()