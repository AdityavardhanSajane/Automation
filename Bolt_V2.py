import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, Text
from ttkthemes import themed_tk as tkk
import json
import os
import subprocess

# Define the available themes
themes = ["dark", "flatly", "lumen", "lux", "minty", "pulse", "sandstone"]

# Default theme
current_theme = "radiance"

def apply_theme(root, theme_name):
    global current_theme
    current_theme = theme_name
    root.set_theme(current_theme)

def import_json():
    global filepath
    filepath = filedialog.askopenfilename(title="Select JSON File", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
    if not filepath:
        return

    with open(filepath, 'r') as file:
        try:
            data = json.load(file)
            edit_json(data)
        except json.JSONDecodeError:
            messagebox.showerror("Error", "Failed to import JSON. The file might be corrupted or not properly formatted.")

def edit_json(data):
    editor_window = tk.Toplevel()
    editor_window.title("Edit JSON")

    def save_changes():
        try:
            updated_data = json.loads(text.get("1.0", tk.END))
            with open(filepath, 'w') as file:
                json.dump(updated_data, file, indent=4)

            branch_url = simpledialog.askstring("Input", "Provide HTTPS URL of the feature branch that you would like to push:")
            if branch_url:
                push_changes_to_git(branch_url, filepath)
                
            editor_window.destroy()

        except json.JSONDecodeError:
            messagebox.showerror("Error", "The JSON structure is not valid. Please correct it before saving.")

    text = Text(editor_window, wrap=tk.WORD)
    text.insert(tk.END, json.dumps(data, indent=4))
    text.pack(expand=1, fill=tk.BOTH)

    save_btn = ttk.Button(editor_window, text="Save Changes", command=save_changes)
    save_btn.pack()

def push_changes_to_git(branch_url, filepath):
    try:
        dir_path = os.path.dirname(filepath)
        os.chdir(dir_path)

        subprocess.check_output(['git', 'add', filepath])
        subprocess.check_output(['git', 'commit', '-m', 'Updated JSON via tool'])
        subprocess.check_output(['git', 'push', branch_url, 'HEAD'])

        messagebox.showinfo("Success", "Changes pushed successfully!")

    except subprocess.CalledProcessError as e:
        messagebox.showerror("Error", f"Failed to push changes. Error: {e.output.decode('utf-8')}")

# Function to get month abbreviation
def get_month_abbreviation(month_num):
    month_mappings = {
        "01": "JAN", "02": "FEB", "03": "MAR", "04": "APR", "05": "MAY", "06": "JUNE",
        "07": "JULY", "08": "AUG", "09": "SEPT", "10": "OCT", "11": "NOV", "12": "DEC",
    }
    return month_mappings.get(month_num, "")

# Function to determine phase type
def determine_phase_type(env_name):
    environment_mapping = {
        "DEV": "DEV", "DIF": "DEV", "SE": "LLE", "PL1": "LLE", "PL2": "LLE",
        "QA": "LLE", "SAPE": "LLE", "UAT": "LLE", "PODA": "PROD", "PODB": "PROD",
        "PODC": "PROD", "PODD": "PROD", "PODE": "PROD", "PODF": "PROD", "DARKPROD": "PROD",
        "DARKPOD": "PROD", "DP": "PROD", "DPROD": "PROD", "PROD": "PROD", "POD": "PROD",
        "PRODUCTION": "PROD", "Prod": "PROD", "Production": "PROD",
    }
    return environment_mapping.get(env_name.strip(), "Unknown")

# Function to submit details and process data
def submit_details(AIT, SPK, OPSnumber, traintype, releasedate, components, env_names, directory, platform):
    release_date_month = releasedate.split(".")[1]
    release_date_year = releasedate.split(".")[0][-2:]
    month_abbreviation = get_month_abbreviation(release_date_month)

    if platform == "Datical":
        release_components = [
            f"{SPK} {component.strip().lower()} {releasedate}:1"
            for component in components
        ]
    else:
        release_components = [
            f"{SPK} {component.strip().lower()} ${'{releaseBranch}:1'}"
            for component in components
        ]

    environments = [
        {
            "environmentName": f"{env.strip()}FOR{month_abbreviation}{release_date_year}" if platform == "Datical" else env.strip(),
            "phaseType": determine_phase_type(env)
        }
        for env in env_names
    ]

    data = {
        "component": {
            "integratedReleaseEnvironments": [f"{env.strip()}FOR{month_abbreviation}{release_date_year}" if platform == "Datical" else env.strip() for env in env_names],
            "releaseComponents": release_components,
            "disableReleaseTrainPreDeployGates": False,
            "disableAllComponentReleaseGates": False,
        },
        "environments": environments,
    }

    create_json_file(data, AIT, SPK, OPSnumber, traintype, releasedate, directory, platform)
    messagebox.showinfo("Success", f"JSON file for Platform {platform} has been created successfully!")

    create_json_file(data, AIT, SPK, OPSnumber, traintype, releasedate, directory, platform)
    messagebox.showinfo("Success", f"JSON file for Platform {platform} has been created successfully!")

# Function to create a JSON file with given data
def create_json_file(data, AIT, SPK, OPSnumber, traintype, releasedate, path, platform):
    if platform == "Datical":
        filename = f"{AIT}_{SPK}_OPSERVICES_{OPSnumber}_DB_{traintype}_Release_Train_{releasedate}.json"
    else:
        filename = f"{AIT}_{SPK}_OPSERVICES_{OPSnumber}_{traintype}_Release_Train_{releasedate}.json"

    with open(f"{path}/{filename}", "w") as file:
        json.dump(data, file, indent=4)

def git_push_to_bitbucket(filepath, https_url):
    try:
        # Navigate to the directory containing the file
        dir_path = os.path.dirname(filepath)
        os.chdir(dir_path)

        # Check if it's already a git repository
        try:
            subprocess.check_call(['git', 'status'])
        except:
            # If not, initialize it as a new git repo
            subprocess.check_call(['git', 'init'])
        
        # Add the file to git
        subprocess.check_call(['git', 'add', filepath])
        
        # Commit the changes
        subprocess.check_call(['git', 'commit', '-m', 'Updated JSON'])
        
        # Set the remote repository
        try:
            subprocess.check_call(['git', 'remote', 'add', 'origin', https_url])
        except subprocess.CalledProcessError:
            # If origin already exists, reset it
            subprocess.check_call(['git', 'remote', 'set-url', 'origin', https_url])
        
        # Push the changes
        subprocess.check_call(['git', 'push', 'origin', 'master'])
        
        messagebox.showinfo("Success", "Successfully pushed to Bitbucket!")
    except subprocess.CalledProcessError as e:
        messagebox.showerror("Error", f"Failed to push to Bitbucket. Error: {e}")

def clear_screen():
    for widget in root.winfo_children():
        widget.destroy()

def launch_tool(platform):
    clear_screen()
    title = ttk.Label(
        root, text="Enter Details", font=("Arial", 24, "bold"), foreground="#007ACC"
    )
    title.pack(pady=30)

    input_frame = ttk.Frame(root)
    input_frame.pack(pady=10, padx=10, fill="both", expand=True)

    labels = [
        "Enter AIT",
        "Enter SPK",
        "Enter OPS Number",
        "Enter Train Type",
        "Enter Release Date",
        "Enter Components (comma separated)",
        "Enter Environments (comma separated)",
    ]
    entries = []

    for idx, label_text in enumerate(labels):
        label = ttk.Label(input_frame, text=label_text, font=("Arial", 12))
        label.grid(row=idx, column=0, padx=10, pady=10, sticky=tk.W)
        entry = ttk.Entry(input_frame, width=40, font=("Arial", 12))
        entry.grid(row=idx, column=1, padx=10, pady=10)
        entries.append(entry)

    def collect_data():
        directory = filedialog.askdirectory(title="Select Directory")
        if not directory:
            return
        AIT, SPK, OPSnumber, traintype, releasedate, components, env_names = (
            e.get() for e in entries
        )
        components = components.split(",")
        env_names = env_names.split(",")
        submit_details(
            AIT, SPK, OPSnumber, traintype, releasedate, components, env_names, directory, platform,
        )

    buttons_frame = ttk.Frame(input_frame)
    buttons_frame.grid(row=len(labels), column=0, columnspan=2, pady=20)

    ttk.Button(buttons_frame, text="Generate JSON", command=collect_data).pack(
        side=tk.LEFT, padx=10
    )
    ttk.Button(buttons_frame, text="Back", command=start_screen).pack(
        side=tk.LEFT, padx=10
    )

def start_screen():
    clear_screen()
    welcome_label = ttk.Label(
        root,
        text="Welcome to Bolt",
        font=("Arial", 30, "bold"),
        foreground="#007ACC",
    )
    welcome_label.pack(pady=60)

    ttk.Button(
        root,
        text="Create JSON for Non-Datical platform",
        command=lambda: launch_tool("Non-Datical"),
        width=40,
    ).pack(pady=15)

    ttk.Button(
        root,
        text="Create JSON for Datical platform",
        command=lambda: launch_tool("Datical"),
        width=40,
    ).pack(pady=15)

    # Button for importing JSON
    ttk.Button(
        root,
        text="Import JSON",
        command=import_json,
        width=40,
    ).pack(pady=15)

root = tkk.ThemedTk()
root.get_themes()
root.set_theme(current_theme)
root.title("Bolt")
root.geometry("700x600")
root.resizable(False, False)

# Dropdown menu for theme selection
theme_var = tk.StringVar()
theme_menu = ttk.Combobox(root, textvariable=theme_var, values=themes)
theme_menu.set(current_theme)
theme_menu.pack(pady=10)
theme_menu.bind("<<ComboboxSelected>>", lambda event, root=root: apply_theme(root, theme_var.get()))

start_screen()
root.mainloop()
