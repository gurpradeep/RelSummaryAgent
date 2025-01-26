import os
import re
from datetime import datetime
import git
from git import Repo, Diff
#from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Optional
from unidiff import PatchSet
from openai import OpenAI 

load_dotenv()

class LocalReleaseNotesGenerator:
    def __init__(self, repo_path, base_tag, target_tag):
        self.repo_path = repo_path
        self.base_tag = base_tag
        self.target_tag = target_tag
        self.repo = git.Repo(repo_path)
        self.openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        self.commits = []
        self.issues = []

    def fetch_data(self):
        """Fetch commits between two tags in local repository"""
        # Get tag references
        #base_commit = self.repo.tags[self.base_tag].commit
        #target_commit = self.repo.tags[self.target_tag].commit

        # Get commits between tags
        #self.commits = list(self.repo.iter_commits(f"{base_commit}..{target_commit}"))
        self.commits = list(self.repo.iter_commits('main', max_count=100))

        # Extract issue numbers from commit messages
        self.issues = list(set(
            int(match.group(1)) 
            for commit in self.commits
            for match in [re.search(r'#(\d+)', commit.message)]
            if match
        ))

    def preprocess_commits(self):
        """Filter and clean commit messages"""
        filtered = []
        for commit in self.commits:
            msg = commit.message
            if msg.startswith(("Merge", "chore(deps)")):
                continue

            # Get conventional commit type
            commit_type = "other"
            for prefix in ["feat", "fix", "docs", "refactor"]:
                if msg.startswith(f"{prefix}:"):
                    commit_type = prefix
                    break

            filtered.append({
                "hexsha": commit.hexsha,
                "message": msg,
                "author": commit.author.name,
                "type": commit_type,
                "diff": self._analyze_diff(commit),
                "issues": self._find_issues_in_message(msg)
            })
        self.commits = filtered

    def _analyze_diff(self, commit):
        """Analyze commit diffs for breaking changes"""
        breaking_changes = []
        if commit.parents:
            diffs = commit.parents[0].diff(commit, create_patch=True)
            
            for diff in diffs:
                if not diff.diff or diff.diff.startswith(b'Binary files'):
                    continue
                diff_text = diff.diff.decode('utf-8')
                try:
                    patch = PatchSet(diff_text)
                    for file in patch:
                        for hunk in file:
                            for line in hunk:
                                if line.is_added and "BREAKING CHANGE" in line.value:
                                    breaking_changes.append(line.value.strip())
                
                except Exception as e:
                    print(f"skipping malformed diff: {e}")
                    continue
        return {"breaking_changes": breaking_changes}
        
    def _find_issues_in_message(self, message):
        """Find issue references in commit messages"""
        return list(set(
            int(match.group(1)) 
            for match in re.finditer(r'#(\d+)', message)
        ))
    

    def _ai_summarize(self, text):
        """Generate release note entries using OpenAI"""
        response = self.openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system",
                  "content":"You are an expert in software release notes. Summarize this into a concise 1-line release note entry. Include issue references like (#123) if present" 
                },
                {"role": "user", "content": text}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    
    '''
    def _ai_summarize(self, text):
        """Generate release note entries using OpenAI"""
        response = self.openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system",
                  "content":"""You are an expert at analyzing git commits for clarity and completeness.
                                Given a commit message, analyze its effectiveness in communicating changes.
                                Return a strict JSON response with exactly these fields as shown in this example:
                                {
                                    "message_clarity": 0.8,
                                    "needs_code_review": false,
                                    "suggested_improvements": ["Add more context about the feature", "Include related ticket numbers"],
                                    "is_breaking_change": false
                                }
                                Important JSON formatting rules:
                                1. message_clarity must be a float between 0 and 1
                                2. needs_code_review must be a boolean
                                3. suggested_improvements must be an array of strings
                                4. is_breaking_change must be a boolean
                                5. Do not add any additional fields
                                6. Keep it as a single-line JSON without pretty printing
                                                                """
                },
                {"role": "user", "content": text}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
        '''

    def generate_notes(self):
        """Generate formatted release notes"""
        categories = {
            "features": [],
            "bug_fixes": [],
            "maintenance": [],
            "breaking_changes": []
        }

        for commit in self.commits:
            entry = {
                "text": self._ai_summarize(commit["message"]),
                "author": commit["author"],
                "issues": commit["issues"]
            }

            if commit["type"] == "feat":
                categories["features"].append(entry)
            elif commit["type"] == "fix":
                categories["bug_fixes"].append(entry)
            elif commit["diff"]["breaking_changes"]:
                categories["breaking_changes"].append({
                    "text": " | ".join(commit["diff"]["breaking_changes"])
                })
            else:
                categories["maintenance"].append(entry)

        return self._format_markdown(categories)

    def _format_markdown(self, categories):
        """Format output as Markdown"""
        date = datetime.now().strftime("%Y-%m-%d")
        output = [
            f"## {self.target_tag} - {date}\n",
            "### 🚀 New Features",
            *[f"- {item['text']} (by {item['author']})" for item in categories["features"]],
            "\n### 🐛 Bug Fixes",
            *[f"- {item['text']}" for item in categories["bug_fixes"]],
            "\n### ⚠️ Breaking Changes",
            *[f"- {item['text']}" for item in categories["breaking_changes"]],
            "\n### 🔧 Maintenance",
            *[f"- {item['text']}" for item in categories["maintenance"]],
        ]
        return "\n".join(output)

if __name__ == "__main__":
    # Example usage
    generator = LocalReleaseNotesGenerator(
        repo_path="../LULCQuant",
        base_tag="v0.0.0",
        target_tag="v1.1.0"
    )
    
    generator.fetch_data()
    generator.preprocess_commits()
    release_notes = generator.generate_notes()
    
    print("Generated Release Notes:\n")
    print(release_notes)