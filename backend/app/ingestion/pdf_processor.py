import os, subprocess, time, urllib.error, urllib.request
from urllib.parse import urlparse
from dotenv import dotenv_values, find_dotenv


def _wait_until_ready(api_url, timeout=60, interval=1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(api_url, timeout=interval)
            return
        except urllib.error.HTTPError:
            return  # server responded (even with an error status), so it's up
        except urllib.error.URLError:
            time.sleep(interval)
    raise TimeoutError(f"mineru-api did not become ready at {api_url} within {timeout}s")


def run_mineru(input_path, output_dir,
               backend="pipeline", method="txt", lang="en",
               api_url="http://127.0.0.1:8000"):

    env = {**os.environ, **dotenv_values(find_dotenv())}

    parsed = urlparse(api_url)
    host, port = parsed.hostname, str(parsed.port)

    server = subprocess.Popen(
        ["uv", "run", "mineru-api", "--host", host, "--port", port],
        env=env,
    )

    try:
        _wait_until_ready(api_url)

        result = subprocess.run([
            "uv", "run", "mineru",
            "-p", input_path,
            "-o", output_dir,
            "-b", backend,
            "--api-url", api_url,
            "-m", method, "-l", lang,
        ])
        if result.returncode != 0:
            raise RuntimeError(f"mineru exited with code {result.returncode}")
    finally:
        server.terminate()
        server.wait()


if __name__ == "__main__":
    run_mineru(
        input_path="backend/storage/documents/doc.pdf",
        output_dir="backend/storage/Artifacts/warm",
    )