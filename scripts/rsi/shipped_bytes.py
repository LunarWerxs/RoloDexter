"""Bytes of the shipped package: committed size at HEAD of src/rolodexter files. Prints shipped_bytes=<n>."""
import subprocess

PREFIX = "src/rolodexter/"
SHIPPED = (".py", ".json", ".typed")
listing = subprocess.run(["git", "ls-tree", "-r", "-l", "-z", "HEAD"], capture_output=True, check=True).stdout
total = 0
for entry in listing.split(b"\0"):
    if not entry:
        continue
    meta, path = entry.decode("utf-8", "replace").split("\t", 1)
    size = meta.split()[3]
    if size != "-" and path.startswith(PREFIX) and path.lower().endswith(SHIPPED):
        total += int(size)
print(f"shipped_bytes={total}")
