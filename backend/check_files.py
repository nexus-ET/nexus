import os

def check_nexus_files():
    target = r"e:\NEXUS\backend\app"
    print(f"--- Checking physical files in {target} ---")
    if not os.path.exists(target):
        print("App directory not found.")
        return
    for root, _, files in os.walk(target):
        for file in files:
            if file.endswith((".py", ".js", ".jsx")):
                print(os.path.join(root, file))

if __name__ == "__main__":
    check_nexus_files()