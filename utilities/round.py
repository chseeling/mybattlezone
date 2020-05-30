import json
from typing import List, Any, Union

with open('../models/digitization01_cleaned.json', "r") as f:
    points = json.load(f)

points_round = []
for point in points:
    points_round.append([round(num, 3) for num in point])

with open("../models/digitization01_cleaned_02.json", 'w') as outfile:
    json.dump(points_round, outfile)
