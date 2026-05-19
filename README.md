# KeepTrack — A Kivy-Based Personal Finance Manager

KeepTrack is a modern personal finance management application developed using **Python**, **Kivy**, and **SQLite**.
The application is designed primarily for Android devices and helps users manage expenses, subscriptions, savings goals, budgets, and financial insights through a clean mobile-first interface.

---

# Features

## Dashboard

* Monthly spending overview
* Remaining budget tracking
* Spending progress visualization
* Recent transaction history
* Budget insight cards
* Subscription summary

## Expense Management

* Add expenses with categories
* Edit existing expenses
* Delete expenses
* Add optional notes
* Date-based expense tracking
* Recurring expense support

## Analytics

* 6-month expense trend visualization
* Financial health scoring
* Spending insights
* Category-wise expense analysis
* Monthly comparison system

## Calendar Heatmap

* Visual expense tracking by date
* Spending intensity visualization
* Daily expense breakdown

## Subscription Tracking

* Manage recurring subscriptions
* Pause/resume subscriptions
* Track billing cycles
* Monthly commitment overview

## Savings Goals

* Create savings goals
* Track completion percentage
* Add savings contributions
* Goal progress visualization

## Settings

* Configure monthly salary
* Configure category budgets
* Currency selection
* Financial preference management

---

# Tech Stack

| Component               | Technology            |
| ----------------------- | --------------------- |
| Frontend                | Python + Kivy         |
| UI Framework            | Kivy / Custom Widgets |
| Database                | SQLite                |
| Android Packaging       | Buildozer             |
| Platform                | Android               |
| Development Environment | Windows               |

---

# Architecture

KeepTrack follows a modular event-driven architecture consisting of:

* UI Layer (Kivy Screens)
* Backend Logic Layer
* SQLite Data Layer
* Android Packaging Layer

Main modules:

* Dashboard
* Analytics
* Calendar
* Goals
* Subscriptions
* Settings
* Expense History
* Expense Management

---

# Screenshots

## Dashboard

* Spending overview
* Budget tracking
* Recent transactions
* Subscription summary

## Analytics

* Monthly spending trends
* Financial health analysis
* Category insights

## Calendar

* Expense heatmap visualization

## Goals

* Savings goal tracking
* Contribution management

## Subscriptions

* Active/paused recurring payments

---

# Database

SQLite is used for local storage of:

* Expenses
* Subscriptions
* Goals
* Budget settings
* Salary settings
* Recurring expense rules

The application works fully offline.

---

# Key Concepts Used

* Event-driven programming
* ScreenManager navigation
* Dynamic widget rendering
* Popup/modal systems
* CRUD operations
* Reusable UI components
* Local database management
* Android APK generation

---

# APK Build

The Android APK is generated using:

* Buildozer
* python-for-android
* Android SDK

---

# Future Enhancements

* Cloud synchronization
* Authentication system
* Notification reminders
* Data backup & restore
* AI-powered financial insights
* Multi-device synchronization
* Online banking integration

---

# Project Type

MCA Final Year Project

---

# Author

Developed as part of MCA academic project work using Python and Kivy for Android-based personal finance management.
