import uvicorn


def run():
    uvicorn.run("stash.api:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
