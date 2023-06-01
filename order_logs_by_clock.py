processes=20

logs = []

for i in range(processes):
    with open(f'{i}log.txt', 'r') as f:
        lines = f.readlines()
    processed_lines = []
    for line in lines:
        if not line:
            continue
        line = line.split('|')
        processed_lines.append([int(line[0]), int(line[1]), line[2]])
    logs += processed_lines

logs.sort(key=lambda x: (x[1],x[0]))

print('rank'.ljust(6), 'clock'.ljust(7), 'message')
for line in logs:
    print(str(line[0]).ljust(6), str(line[1]).ljust(7), line[2], end='')
