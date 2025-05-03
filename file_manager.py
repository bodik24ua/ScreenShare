import os
import random
import string

MONITOR_INDEX_FILE = "AirVerse_ScreenShare_Monitor.txt"
CODE_FILE = "AirVerse_ScreenShare_PassKey.txt"
MIN_CODE_LENGTH = 4
MAX_CODE_LENGTH = 5

def get_documents_path():
    return os.path.expanduser("~/Documents")

def generate_code(min_length=MIN_CODE_LENGTH, max_length=MAX_CODE_LENGTH):
    length = random.randint(min_length, max_length)
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def load_or_generate_code():
    documents_path = get_documents_path()
    code_file_path = os.path.join(documents_path, CODE_FILE)

    if os.path.exists(code_file_path):
        with open(code_file_path, "r") as f:
            code = f.readline().strip()
            if code:
                return code.upper()

    code = generate_code()
    with open(code_file_path, "w") as f:
        f.write(code + "\n")
    return code

def save_selected_monitor_index(index):
    documents_path = get_documents_path()
    index_file_path = os.path.join(documents_path, MONITOR_INDEX_FILE)
    try:
        with open(index_file_path, "w") as f:
            f.write(str(index + 1))
        print(f"[FILE_MANAGER] Saved selected monitor index: {index + 1}")
    except Exception as e:
        print(f"[FILE_MANAGER] Error saving monitor index: {e}")

def load_selected_monitor_index():
    documents_path = get_documents_path()
    index_file_path = os.path.join(documents_path, MONITOR_INDEX_FILE)
    try:
        with open(index_file_path, "r") as f:
            return int(f.readline().strip()) - 1
    except (FileNotFoundError, ValueError):
        print("[FILE_MANAGER] Could not load monitor index from file. Defaulting to monitor 0.")
        return 0 
    except Exception as e:
        print(f"[FILE_MANAGER] Error loading monitor index: {e}. Defaulting to monitor 0.")
        return 0

if __name__ == "__main__":
    code = load_or_generate_code()
    print(f"Generated/Loaded Code: {code}")