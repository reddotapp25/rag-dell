import tkinter as tk
from tkinter import filedialog, messagebox
import os
import re

class FileRestorerApp:
    """A Tkinter application to select a markdown backup file and restore its contents."""

    # Regex to capture content in a Markdown code block:
    # (?s) enables DOTALL mode, so . matches newlines
    # ```(.*?)\n: Captures the language tag (group 1, unused for restoration)
    # (.*?)```: Captures the file content (group 2)
    MD_BLOCK_REGEX = re.compile(r'```(.*?)\n(.*?)\n```', re.DOTALL)

    def __init__(self, master):
        self.master = master
        master.title("Code Restoration Tool")
        
        # Adjusting geometry slightly for a clean look without being overwhelming
        master.geometry("400x160")
        master.resizable(False, False)

        # Set default working directory for file dialog
        self.initial_dir = os.getcwd()

        # UI elements
        self.label = tk.Label(master, text="Select the backup Markdown file (.md) to restore:", pady=10)
        self.label.pack()

        self.select_button = tk.Button(
            master, 
            text="Select File & Restore", 
            command=self.select_file, 
            bg="#2563eb", 
            fg="white", 
            padx=10, 
            pady=5
        )
        self.select_button.pack(pady=15)

        self.status_label = tk.Label(master, text="Awaiting file selection...", fg="#004d40")
        self.status_label.pack()

    def select_file(self):
        """Opens a file dialog for the user to select the Markdown backup file."""
        file_path = filedialog.askopenfilename(
            initialdir=self.initial_dir,
            title="Select Backup Markdown File",
            filetypes=(("Markdown files", "*.md"), ("All files", "*.*"))
        )

        if file_path:
            self.status_label.config(text=f"Processing: {os.path.basename(file_path)}...", fg="orange")
            self.master.update()
            self.process_markdown_file(file_path)
        else:
            self.status_label.config(text="File selection cancelled.", fg="red")

    def write_file_to_destination(self, path, content) -> bool:
        """Creates directories and writes the content to the specified file path."""
        try:
            # 1. Create the directory if it does not exist
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            
            # 2. Write the content
            with open(path, 'w', encoding='utf-8') as f:
                # Use strip() on content before writing to remove extra leading/trailing whitespace 
                # from the parsing process, but add a final newline for a proper file termination.
                f.write(content.strip() + '\n') 
            return True
        except Exception as e:
            messagebox.showerror("File Write Error", f"Failed to write file {path}: {e}")
            print(f"Error writing file {path}: {e}")
            return False

    def process_markdown_file(self, file_path):
        """Reads the Markdown file, extracts code blocks, cleans content, and writes files."""
        restored_count = 0
        total_count = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Read Error", f"Failed to read file: {e}")
            self.status_label.config(text="Read error occurred.", fg="red")
            return

        # Use regex to find all code blocks
        matches = self.MD_BLOCK_REGEX.findall(content)

        if not matches:
            messagebox.showwarning("Parse Warning", "No code blocks found in the selected file. Restoration stopped.")
            self.status_label.config(text="No code blocks found.", fg="red")
            return
            
        total_count = len(matches)

        for _, block_content in matches:
            lines = block_content.split('\n')

            if not lines:
                continue

            # 1. Extract the file path from the first line 
            header_line = lines[0].strip()
            
            # Skip blocks that don't look like file headers
            if not header_line.startswith(('#', '//')):
                continue

            try:
                # Find the path by skipping the comment prefix and whitespace
                path_start_index = header_line.find(' ') + 1
                file_path_unix = header_line[path_start_index:].strip()
                
                # Convert Unix-style path in MD to OS-native path
                destination_path = file_path_unix.replace('/', os.path.sep)
            except IndexError:
                print(f"Skipping block due to malformed header: {header_line}")
                continue
            
            # 2. Clean the content: Remove the header (first line) and EOF marker (last line)
            
            # Remove trailing empty strings/newlines
            while lines and not lines[-1].strip():
                lines.pop()

            # Remove EOF line (last line) if it matches the marker inserted by backup.py
            if lines and lines[-1].strip().endswith("end_of_file"):
                lines.pop()
            
            # Remove Header line (first line)
            if lines:
                lines.pop(0)

            # Re-join content, preserving the newlines
            file_content = '\n'.join(lines)

            # 3. Write the file
            if destination_path and self.write_file_to_destination(destination_path, file_content):
                restored_count += 1

        # 4. Display results
        if restored_count > 0:
            messagebox.showinfo("Restoration Complete", 
                                f"Successfully restored {restored_count} of {total_count} file blocks to their original directories.")
            self.status_label.config(text=f"Restored {restored_count} files successfully.", fg="green")
        else:
            messagebox.showwarning("Restoration Failed", 
                                   f"Could not restore any files. Check if the Markdown file format is correct.")
            self.status_label.config(text="Restoration failed.", fg="red")


def main():
    root = tk.Tk()
    app = FileRestorerApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()