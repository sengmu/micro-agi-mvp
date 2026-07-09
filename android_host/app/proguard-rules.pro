# Keep WebView / JS bridge for desktop pet
-keepclassmembers class com.sg.magi.PetOverlayService$PetBridge {
    @android.webkit.JavascriptInterface <methods>;
}
