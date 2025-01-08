import pandas as pd
import random
import math
import re
from collections import defaultdict
import sys
import traceback

# File paths
winnings_file = "cumulative_winnings.csv"  # File to store cumulative winnings
sheet_url = "https://docs.google.com/spreadsheets/d/xxxx"  # Replace with actual Google Sheet URL

# Category item limits
CATEGORY_LIMITS = {
    "Insignias [Red]": 28,
    "Insignias [Yellow]": 28,
    "Selection cards": {"Hero Selection card": 1, "Relic Selection card": 1},
    "Stones": {"T2 Stone": 4, "T1 Stone": 3, "Recast Stone": 4}
}

def fetch_google_sheet_data(sheet_url):
    """Fetch data from the Google Sheet."""
    try:
        sheet_id = sheet_url.split("/")[5]
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        return pd.read_csv(export_url)
    except Exception as e:
        print("Error fetching Google Sheet data:", e)
        traceback.print_exc()
        sys.exit(1)  # Exit if data fetching fails

def load_previous_winnings():
    """Load cumulative winnings per category from the CSV file."""
    try:
        df = pd.read_csv(winnings_file)
        winnings_tracker = defaultdict(lambda: defaultdict(int))
        for _, row in df.iterrows():
            category = row['category']
            member = row['member']
            total_winnings = row['total_winnings']
            winnings_tracker[category][member] = total_winnings
        return winnings_tracker
    except FileNotFoundError:
        print(f"Warning: {winnings_file} not found. Starting with empty winnings.")
        return defaultdict(lambda: defaultdict(int))
    except Exception as e:
        print("Error loading previous winnings:", e)
        traceback.print_exc()
        sys.exit(1)

def parse_participants(data):
    """Parse participants and their latest choices from the fetched data."""
    try:
        categories = ['Insignias [Red]', 'Insignias [Yellow]', 'Selection cards', 'Stones']

        # Convert timestamp to datetime for sorting
        data['Tidsstempel'] = pd.to_datetime(data['Tidsstempel'], format="%d/%m/%Y %H.%M.%S")
        # Sort data by timestamp in descending order and keep only the latest entry per participant
        latest_entries = data.sort_values('Tidsstempel', ascending=False).drop_duplicates('username')

        participants = defaultdict(lambda: defaultdict(list))
        for _, row in latest_entries.iterrows():
            member = row['username']
            
            # Parse Insignias as integers (1 or 2 items)
            for category in ['Insignias [Red]', 'Insignias [Yellow]']:
                if pd.notna(row[category]):
                    participants[member][category] = int(float(row[category]))  # Convert to integer
            
            # Parse Selection cards and Stones as lists of specific items
            for category in ['Selection cards', 'Stones']:
                items = str(row[category]).split(",") if pd.notna(row[category]) else []
                items = [item.strip() for item in items]  # Clean up whitespace
                participants[member][category].extend(items)

        return participants
    except Exception as e:
        print("Error parsing participants data:", e)
        traceback.print_exc()
        sys.exit(1)

def distribute_items(participants_choices, winnings_tracker):
    """Distribute items fairly among participants using improved weighted random selection."""
    allocation = []  # Store allocation results
    participant_item_count = defaultdict(int)  # Track how many items each participant has won

    try:
        for category, limit in CATEGORY_LIMITS.items():
            if isinstance(limit, int):  # Fixed-limit categories (e.g., Insignias)
                category_participants = [
                    [p, participants_choices[p][category]]  # Use the requested number of items directly (1 or 2)
                    for p in participants_choices if category in participants_choices[p]
                ]

                items = [f"{category} #{i+1}" for i in range(limit)]
                items.sort(key=numeric_sort_key)  # Ensure items are sorted numerically

                if not category_participants:
                    # If no participants, mark all items as "First Come, First Serve"
                    allocation.extend([(item, "First Come, First Serve") for item in items])
                    continue

                # First pass: Distribute one item per participant who requested at least one
                first_pass_participants = [p for p, max_items in category_participants if max_items >= 1]
                for participant in first_pass_participants:
                    if items:
                        item = items.pop(0)
                        allocation.append((item, participant))
                        winnings_tracker[category][participant] += 1
                        participant_item_count[participant] += 1

                # Compute average winnings for dynamic boosting
                average_winnings = (
                    sum(winnings_tracker[category].values()) / len(winnings_tracker[category])
                    if len(winnings_tracker[category]) > 0 else 0
                )

                # Second pass: Distribute remaining items based on improved weights
                second_pass_participants = [
                    p for p, max_items in category_participants if max_items == 2 and participant_item_count[p] < 2
                ]
                while items:
                    if not second_pass_participants:
                        break

                    # Calculate improved weights (logarithmic scaling + dynamic boost)
                    weights = [
                        (1 / (1 + math.log(1 + winnings_tracker[category].get(p, 0)))) *
                        (1.5 if winnings_tracker[category].get(p, 0) < average_winnings else 1)
                        for p in second_pass_participants
                    ]
                    winner = random.choices(second_pass_participants, weights=weights, k=1)[0]

                    # Allocate item to the winner
                    item = items.pop(0)
                    allocation.append((item, winner))
                    winnings_tracker[category][winner] += 1
                    participant_item_count[winner] += 1

                    # Remove winner from second pass if they now have two items
                    if participant_item_count[winner] == 2:
                        second_pass_participants.remove(winner)

                # If there are still unallocated items, mark them as "First Come, First Serve"
                if items:
                    allocation.extend([(item, "First Come, First Serve") for item in items])

            elif isinstance(limit, dict):  # Subcategories (e.g., Stones, Selection cards)
                for subcategory, sub_limit in limit.items():
                    subcategory_participants = [
                        [p, min(2, len([item for item in participants_choices[p][category] if item == subcategory]))]
                        for p in participants_choices if category in participants_choices[p]
                    ]

                    items = [f"{subcategory} #{i+1}" for i in range(sub_limit)]
                    items.sort(key=numeric_sort_key)  # Ensure items are sorted numerically

                    if not subcategory_participants:
                        # If no participants, mark all items as "First Come, First Serve"
                        allocation.extend([(item, "First Come, First Serve") for item in items])
                        continue

                    # Compute average winnings for dynamic boosting
                    average_winnings = (
                        sum(winnings_tracker[subcategory].values()) / len(winnings_tracker[subcategory])
                        if len(winnings_tracker[subcategory]) > 0 else 0
                    )

                    while items:
                        # Filter out participants who reached their max items
                        active_participants = [p for p in subcategory_participants if p[1] > 0]
                        if not active_participants:
                            break

                        # Calculate improved weights (logarithmic scaling + dynamic boost)
                        weights = [
                            (1 / (1 + math.log(1 + winnings_tracker[subcategory].get(p[0], 0)))) *
                            (1.5 if winnings_tracker[subcategory].get(p[0], 0) < average_winnings else 1)
                            for p in active_participants
                        ]
                        winner_index = random.choices(range(len(active_participants)), weights=weights, k=1)[0]
                        winner = active_participants[winner_index][0]

                        # Allocate item to the winner
                        item = items.pop(0)
                        allocation.append((item, winner))
                        winnings_tracker[subcategory][winner] += 1

                        # Update max items for the winner
                        active_participants[winner_index][1] -= 1

                    # If there are still unallocated items, mark them as "First Come, First Serve"
                    if items:
                        allocation.extend([(item, "First Come, First Serve") for item in items])

        return allocation
    except Exception as e:
        print("Error during item distribution:", e)
        traceback.print_exc()
        sys.exit(1)


def update_winnings_file(winnings_tracker):
    """Update the cumulative winnings file."""
    try:
        records = []
        for category, members in winnings_tracker.items():
            for member, total_winnings in members.items():
                records.append({'category': category, 'member': member, 'total_winnings': total_winnings})
        
        df = pd.DataFrame(records)
        df.to_csv(winnings_file, index=False)
    except Exception as e:
        print("Error updating winnings file:", e)
        traceback.print_exc()
        sys.exit(1)



def numeric_sort_key(item):
    """Extract numeric part of the item for proper numeric sorting."""
    match = re.search(r"#(\d+)", item)
    return int(match.group(1)) if match else float('inf')


def write_output(allocation):
    """Write the allocation result to a CSV file in the desired format."""
    try:
        formatted_allocation = []

        for item, winner in allocation:
            if "Red Insignia" in item:
                formatted_category = "Red Insignia"
            elif "Yellow Insignia" in item:
                formatted_category = "Yellow Insignia"
            elif "Selection card" in item:
                formatted_category = "Selection card"
            else:
                formatted_category = "Stone"

            formatted_allocation.append((item, winner))

        # Write to CSV
        df = pd.DataFrame(formatted_allocation, columns=['Item', 'Winner'])
        df.to_csv("weekly_allocation.csv", index=False)
        print("\nAllocation results written to 'weekly_allocation.csv'")
    except Exception as e:
        print("Error writing output file:", e)
        traceback.print_exc()
        sys.exit(1)

def main():
    try:
        # Load cumulative winnings from previous weeks
        winnings_tracker = load_previous_winnings()
        
        # Fetch and parse participants data from Google Sheet
        data = fetch_google_sheet_data(sheet_url)
        participants = parse_participants(data)
        
        # Distribute items fairly and get the allocation result
        allocation = distribute_items(participants, winnings_tracker)
        
        # Update the cumulative winnings file
        update_winnings_file(winnings_tracker)
        
        # Write the allocation result to a CSV file
        write_output(allocation)
    except Exception as e:
        print("Error in main function:", e)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
