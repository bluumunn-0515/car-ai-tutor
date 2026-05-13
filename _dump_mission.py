p = r"c:/Users/user/Documents/car-diagnostic-app/app.py"
with open(p, encoding="utf-8") as f:
    lines = f.readlines()
out = r"c:/Users/user/Documents/car-diagnostic-app/_snippet_mission.txt"
with open(out, "w", encoding="utf-8") as w:
    w.writelines(lines[1085:1285])
print("ok")
