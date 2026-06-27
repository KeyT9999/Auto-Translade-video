import os

path = r"d:\MMO\tutuaz"
print("Path:", path)
print("Exists:", os.path.exists(path))
if os.path.exists(path):
    print("Is directory:", os.path.isdir(path))
    print("Is file:", os.path.isfile(path))
    if os.path.isdir(path):
        print("Contents:")
        for f in os.listdir(path):
            fpath = os.path.join(path, f)
            print(f"- {f} (Dir: {os.path.isdir(fpath)}, Size: {os.path.getsize(fpath) if os.path.isfile(fpath) else 'N/A'})")
    else:
        print("Size:", os.path.getsize(path))
        # print first 100 bytes
        with open(path, "rb") as f:
            print("Header:", f.read(100))
