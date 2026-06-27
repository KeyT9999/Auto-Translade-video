with open("pipeline_vi.py", "r", encoding="utf-8") as f:
    content = f.read()

print("File size:", len(content))
keywords = ["srt", "generate_srt", "subtitle", "srt_generator"]
for kw in keywords:
    print(f"Keyword '{kw}' occurs: {content.lower().count(kw)}")
    
# Let's print lines matching "srt"
print("\nMatching lines:")
lines = content.splitlines()
for i, line in enumerate(lines):
    if "srt" in line.lower() or "subtitle" in line.lower():
        print(f"Line {i+1}: {line}")
