# PLP Detection Testing Framework

This testing framework is designed to evaluate the performance of different Large Language Models (LLMs) in identifying Product Listing Pages (PLPs) from HTML content.

## Setup

1.  **Install Dependencies:**
    Navigate to the `testing` directory and install the required Python packages.
    ```bash
    pip install -r requirements.txt
    ```

2.  **Set Environment Variables:**
    You need to set your OpenAI API key as an environment variable. Create a `.env` file in the `testing` directory and add your key:
    ```
    OPENAI_API_KEY="your_openai_api_key"
    ```
    The script `test_plp_detection.py` will load this key.

## Running the Tests

To run the tests, execute the `test_plp_detection.py` script from the root of the project:

```bash
python testing/test_plp_detection.py
```

The script will iterate through the models defined in `MODELS_TO_TEST` and for each model, it will process all the `_cleaned.html` files in the `test_html_outputs` directory. The output will indicate whether each file is classified as a PLP by the model. 