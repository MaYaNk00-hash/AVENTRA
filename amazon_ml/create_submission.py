import subprocess
import sys
import os

print("Running validation script...")
val_cmd = [
    sys.executable,
    "utils/validate_submission.py",
    "--matching", "output/matching_results.tsv",
    "--candidate", "output/candidate_pairs.tsv",
    "--test-dir", "dataset/test"
]

val_res = subprocess.run(val_cmd, capture_output=True, text=True)
print(val_res.stdout)
print(val_res.stderr)

if val_res.returncode == 0:
    print("Validation passed! Creating submission zip...")
    zip_cmd = [
        "powershell", "-Command",
        "Compress-Archive -Path output, code, Documentation_template.md -DestinationPath TeamAntigravity_submission.zip -Force"
    ]
    zip_res = subprocess.run(zip_cmd, capture_output=True, text=True)
    if zip_res.returncode == 0:
        print("Successfully created TeamAntigravity_submission.zip")
    else:
        print("Failed to create zip:", zip_res.stderr)
else:
    print("Validation failed. Please fix issues before zipping.")
