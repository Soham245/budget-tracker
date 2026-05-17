[app]

title = Budget Tracker
package.name = budgettracker
package.domain = org.soham

source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,ttf

version = 1.0

requirements = requirements = python3,kivy==2.3.0,pillow

orientation = portrait

fullscreen = 0

android.api = 31
android.minapi = 21
android.sdk = 31
android.ndk = 25b
android.accept_sdk_license = True

[buildozer]

log_level = 2
warn_on_root = 1