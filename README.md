# Poll Game Flask App

A fully functioning local Flask app for running a live poll-style quiz game. Players join from their phones by entering a name and email, then answer multiple-choice questions in real time. The host screen shows questions, options, countdown status, bar-chart results after each question, and a CSV download after the game ends.

## Quick start

1. Unzip this folder.
2. Open a terminal in the unzipped folder.
3. Create and activate a virtual environment, recommended:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Run the app:

```bash
python app.py
```

6. Open the host screen on the computer:

```text
http://localhost:5000
```

7. Have players join from their phones using the network URL shown on the host screen, usually something like:

```text
http://YOUR-COMPUTER-IP:5000/join
```

## Notes

- The app uses in-memory storage. Restarting the server resets the game.
- Edit `questions.json` to customize the quiz. Each question needs a `question` string and an `options` list.
- Each question stays open until every joined player answers or 10 seconds passes, whichever comes first.
- A CSV download button appears after all questions have completed.

## File structure

```text
app.py
questions.json
requirements.txt
README.md
templates/
  host.html
  join.html
  player.html
static/
  style.css
```
