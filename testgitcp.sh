#!/bin/bash
 
# Get the current repo and branch
current_repo=$(git remote -v | awk 'NR==1{print $2}')
current_branch=$(git symbolic-ref --short HEAD)

echo "Current repository: $current_repo"
echo "Current branch: $current_branch"

# Ask if changes to repo URL are needed
read -p "Do you want to change the repository URL? (yes/no): " change_repo

if [ "$change_repo" == "yes" ]; then
    read -p "Enter the new repository URL: " new_repo
    git remote set-url origin "$new_repo"
    git fetch
    echo "Repository URL changed to: $new_repo"
fi

# Ask if changes to branch are needed
read -p "Do you want to change the branch? (yes/no): " change_branch

if [ "$change_branch" == "yes" ]; then
    read -p "Enter the new branch name: " new_branch
    git checkout "$new_branch"
    echo "Switched to branch: $new_branch"
fi

# Confirm current repo and branch
read -p "Is the current repository and branch correct? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Please make the necessary changes and re-run the script."
    exit 1
fi

# Show git status
git status

# Ask if changes should be added
read -p "Do you want to add the changes? (yes/no): " add_changes

if [ "$add_changes" == "yes" ]; then
    git add .
    echo "Changes added."
fi

# Get commit message
read -p "Enter the commit message: " commit_message

# Commit the changes
git commit -m "$commit_message"
echo "Changes committed."

# Show git status
git status

# Ask if changes should be pushed
read -p "Do you want to push the changes to the current branch? (yes/no): " push_changes

if [ "$push_changes" == "yes" ]; then
    git push origin "$current_branch"
    echo "Changes pushed to $current_branch."
fi

echo "Script completed."
