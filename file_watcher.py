from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import time
import shutil

VAULT_PATH = Path("ai_employee_vault")
INBOX = VAULT_PATH / "inbox"
NEEDS_ACTION = VAULT_PATH / "needs_action"
DONE = VAULT_PATH / "done"
LOGS = VAULT_PATH / "logs"

class InboxHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        print(f"New task received: {file_path.name}")

        destination = NEEDS_ACTION / file_path.name
        shutil.move(str(file_path), destination)
        print(f"Moved to needs_action: {destination.name}")

        self.log_activity(file_path.name)

    def log_activity(self, filename):
        LOGS.mkdir(exist_ok=True)
        log_file = LOGS / "watcher.log"
        with open(log_file, "a") as f:
            f.write(f"{time.ctime()} - Task moved to needs_action: {filename}\n")

if __name__ == "__main__":
    INBOX.mkdir(parents=True, exist_ok=True)
    NEEDS_ACTION.mkdir(exist_ok=True)
    DONE.mkdir(exist_ok=True)

    event_handler = InboxHandler()
    observer = Observer()
    observer.schedule(event_handler, str(INBOX), recursive=False)
    observer.start()

    print("Watcher is running... Monitoring /inbox")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
