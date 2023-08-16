import subprocess

def main():
    commands = [
        "gh",
        "pr",
        "list"
    ]
    subprocess.run(commands)

if __name__ == "__main__":
    main()