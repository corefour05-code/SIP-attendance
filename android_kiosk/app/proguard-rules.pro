# ProGuard rules for AndroidUSBCamera and Gson
-keep class com.serenegiant.** { *; }
-keep class com.jiangdg.** { *; }
-keep class com.sip.kiosk.Models.** { *; }
-keepclassmembers class * {
    @com.google.gson.annotations.SerializedName <fields>;
}

