#!/bin/bash

# Navigate to project directory
cd "/Users/praxzz/Downloads/examguard 7"

# Add all files
git add -A

# Commit
git commit -m "Initial ExamGuard project with trust-based exam proctoring system"

# Set remote URL
git remote add origin https://github.com/911123104034praxzz06/qqq.git

# Rename branch to main if needed
git branch -M main

# Push to GitHub
git push -u origin main

echo "✅ Successfully pushed to GitHub!"
