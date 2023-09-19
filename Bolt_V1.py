import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ttkthemes import themed_tk as tkk
import json

def submit_details(AIT, SPK, OPSnumber, traintype, releasedate, components, env_names, directory, platform):
    release_date_month = releasedate.split(".")[1]
    release_date_year = releasedate.split(".")[0][-2:]
    month_mappings = {
        "01": "JAN",
        "02": "FEB",
        "03": "MAR",
        "04": "APR",
        "05": "MAY",
        "06": "JUNE",
        "07": "JULY",
        "08": "AUG",
        "09": "SEPT",
        "10": "OCT",
        "11": "NOV",
        "12": "DEC",
    }
    month_abbreviation = month_mappings.get(release_date_month, "")

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
            "phaseType": determine_phase_type(env, platform)
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

def determine_phase_type(env_name, platform):
    mapping_NonDatical = {
        "DEV": "DEV",
        "DIF": "DEV",
        "SE": "LLE",
        "PL1": "LLE",
        "PL2": "LLE",
        "QA": "LLE",
        "SAPE": "LLE",
        "UAT": "LLE",
        "PODA": "PROD",
        "PODB": "PROD",
        "PODC": "PROD",
        "PODD": "PROD",
        "PODE": "PROD",
        "PODF": "PROD",
        "DARKPROD": "PROD",
        "DARKPOD": "PROD",
        "DP": "PROD",
        "DPROD": "PROD",
        "PROD": "PROD",
        "POD": "PROD",
        "PRODUCTION": "PROD",
        "Prod": "PROD",
        "Production": "PROD",
    }
    
    return mapping_NonDatical.get(env_name.strip(), "Unknown")

def create_json_file(data, AIT, SPK, OPSnumber, traintype, releasedate, path, platform):
    if platform == "Datical":
        filename = f"{AIT}_{SPK}_OPSERVICES_{OPSnumber}_DB_{traintype}_Release_Train_{releasedate}.json"
    else:
        filename = f"{AIT}_{SPK}_OPSERVICES_{OPSnumber}_{traintype}_Release_Train_{releasedate}.json"

    with open(f"{path}/{filename}", "w") as file:
        json.dump(data, file, indent=4)


def main():
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
                AIT,
                SPK,
                OPSnumber,
                traintype,
                releasedate,
                components,
                env_names,
                directory,
                platform,
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

    root = tkk.ThemedTk()
    root.get_themes()
    root.set_theme("radiance")
    root.title("Bolt")
    root.geometry("700x600")
    root.resizable(False, False)

    start_screen()
    root.mainloop()

if __name__ == "__main__":
    main()
