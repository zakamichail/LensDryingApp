from app import create_app
from os import getenv

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(getenv("PORT", "5055")), debug=True)
