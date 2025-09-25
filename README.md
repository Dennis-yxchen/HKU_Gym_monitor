# HKU Fitness Centre Monitor

A desktop application designed for HKU students and staff to monitor real-time availability of peak-time slots at the university’s fitness centres.

## Overview

This tool automatically fetches the latest booking information from the [HKU Fitness Centre booking website](https://fcbooking.cse.hku.hk/) and displays session availability for **CSE Active** and **HKU B-Active** in an easy-to-read table. Users can select specific time slots they’re interested in, and the app will continuously monitor those slots in the background.

When a selected slot changes from **"Full"** to **available**, the application immediately shows a desktop alert notification and automatically removes the slot from monitoring to prevent repeated alerts.

The app helps HKU community members secure popular workout sessions without manually refreshing the booking page, especially during high-demand periods when slots open **3 days in advance at 12:00 PM daily**.

> **Note**: Booking is only required for **peak hours** at CSE Active and B-Active. Walk-ins are allowed during off-peak times and at SHSC Fitness Centre. Always bring your HKU staff/student card for facility access.
