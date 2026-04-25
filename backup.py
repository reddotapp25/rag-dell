# backup.py
import os
from collections import defaultdict
import re

# --- Secret Masking Configuration (ONLY applied to .env and .env.local) ---
PLACEHOLDER = '<REPLACE_WITH_ACTUAL_VALUE>'
# Regex to find the key, assignment operator/colon, and optional quotes, then replace the rest of the value.
# Group 1: The prefix up to the assignment/colon and optional opening quote (e.g., 'VITE_KEY="', 'config: "').
# Group 2: The suffix (optional closing quote/terminator).
MASKING_REGEX = re.compile(r'([^=:]*[=:]\s*["\']?).*?([;,\s"\'\n]*)$')

def get_comment_prefix_and_language(filename):
    """Determines the appropriate comment prefix and code block language based on file extension."""
    if filename.endswith(('.py', '.txt', '.env', '.ini')):
        # Use 'python' for .env files as they share key=value syntax
        return '#', 'python'
    elif filename.endswith(('.ts', '.tsx', '.js', '.jsx')):
        return '//', 'tsx'
    elif filename.endswith(('.css')):
        return '//', 'css'
    elif filename.endswith(('.html')):
        return '//', 'html'
    elif filename.endswith(('.json')):
        return '//', 'json' 
        
    # Default for unknown extensions
    return '#', 'py' 

def mask_secrets(line: str) -> str:
    """
    Masks the value part of a key-value assignment in environment files.
    This function is ONLY called if the filename is .env or .env.local.
    """
    
    # We rely on the caller (process_file_content) to ensure this is an .env file.
    
    # Use re.sub with a lambda function to replace the value part
    def replace_value(match):
        prefix = match.group(1)
        suffix = match.group(2)
        
        # Simple fix for potential double-quotes if value was quoted
        if prefix.endswith('"') and suffix.startswith('"') and suffix.count('"') == 1:
            suffix = suffix[1:] 

        return f"{prefix}{PLACEHOLDER}{suffix}"

    # Only apply the regex if an assignment is present, ensuring we don't break comments or headers
    if re.search(r'[=:]', line):
        return MASKING_REGEX.sub(replace_value, line)
    
    return line


def process_file_content(full_path, root_dir):
    """
    Reads a file, conditionally masks secrets, ensures it has the correct path header and EOF marker,
    and formats it into a complete Markdown code block.
    """
    # 1. Determine the relative path, comment, and language
    filename = os.path.basename(full_path)
    relative_path = os.path.relpath(full_path, start='.')
    comment_prefix, language_tag = get_comment_prefix_and_language(full_path)
    
    # Standardize the path comment format using forward slashes
    relative_path_unix = relative_path.replace(os.path.sep, '/')
    expected_header = f"{comment_prefix} {relative_path_unix}"
    
    # Determine if masking is required
    is_env_file = filename in ['.env', '.env.local']
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # 2. Conditional Secret Masking (New logic)
        if is_env_file:
            print(f"Masking secrets in sensitive file: {filename}")
            masked_lines = [mask_secrets(line) for line in lines]
            content_lines = masked_lines
        else:
            content_lines = lines # Use original lines without masking

        # 3. Check and handle the header line (Prevents Duplication)
        if not content_lines or content_lines[0].strip() != expected_header.strip():
            # Header is missing or incorrect; prepend the required header
            content_lines = [expected_header + '\n'] + content_lines

        # 4. Check and handle the end_of_file line
        end_of_file_marker_line = f"\n{comment_prefix} end_of_file" 
        
        # Clean up existing EOF marker and trailing newlines for normalization
        while content_lines and content_lines[-1].strip().endswith("end_of_file"):
             content_lines.pop()
        while content_lines and content_lines[-1].strip() == "":
             content_lines.pop()
        
        # Add the standardized EOF marker
        content_lines.append(end_of_file_marker_line)

        # 5. Format the output with the required code block fences 
        file_content_string = "".join(content_lines)
        
        markdown_block = (
            f"```{(language_tag or '')}\n"
            f"{file_content_string.strip()}\n" 
            f"```"
        )
        
        return markdown_block
    
    except Exception as e:
        print(f"Error processing file {full_path}: {e}")
        return "" 

def generate_documentation(root_dirs):
    """Scans root directories and generates the required Markdown files."""
    
    # Directories to be ignored during the scan
    EXCLUDED_DIRS = ['node_modules', '__pycache__', 'dist', 'build', '.vite', '.git', 'coverage', '.venv', 'venv']

    # Store collected content, keyed by the root directory name
    collected_content = defaultdict(list)
    
    # Iterate through specified root directories
    for root_dir in root_dirs:
        print(f"Scanning directory: {root_dir}")
        for dirpath, dirnames, filenames in os.walk(root_dir):
            
            # Exclusion: Remove specified directories from the list of directories to walk into
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            
            # Process files in the current directory
            for filename in filenames:
                # Basic check to skip common non-code files and artifacts
                if filename in ['.DS_Store', 'Thumbs.db', 'package-lock.json', 'yarn.lock']:
                    continue
                
                # Skip source maps and compiled artifacts
                if filename.endswith(('.map', '.log', '.pyc', '.orig')):
                    continue

                full_path = os.path.join(dirpath, filename)
                
                # Process and collect the content as a complete Markdown code block
                markdown_block = process_file_content(full_path, root_dir)
                if markdown_block:
                    collected_content[root_dir].append(markdown_block)

    # Write the collected content to Markdown files
    for root_dir, blocks in collected_content.items():
        output_filename = f"{root_dir}.md"
        
        # Join all blocks with a double newline for clear separation between code blocks
        final_markdown_output = '\n\n'.join(blocks)
        
        # Write to the final markdown file
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_markdown_output + '\n') 
            
        print(f"Successfully generated {output_filename}")

if __name__ == "__main__":
    # Define the directories to scan relative to where the script is run
    directories_to_scan = ['backend', 'frontend']
    generate_documentation(directories_to_scan)