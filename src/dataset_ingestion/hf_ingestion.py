import json
import sys
from pathlib import Path

import boto3

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.items import Item

LITE_MODE = True
username = "ed-donner"
dataset_name = "items_lite" if LITE_MODE else "items_full"
dataset = f"{username}/{dataset_name}"

train, val, test = Item.from_hub(dataset)
print(
    f"Loaded {len(train):,} training items, {len(val):,} validation items, "
    f"{len(test):,} test items"
)

s3 = boto3.client("s3")
bucket = "my-product-data-194722416872"
prefix = f"{dataset_name}/"

def upload_split(name, items):
    lines = []
    for item in items:
        lines.append(json.dumps({
            "summary": item.summary,
            "category": item.category,
            "price": item.price,
        }))
    s3.put_object(
        Bucket=bucket,
        Key=f"{prefix}{name}.jsonl",
        Body="\n".join(lines).encode("utf-8"),
        ContentType="application/json",
    )

upload_split("train", train)
upload_split("val", val)
upload_split("test", test)
