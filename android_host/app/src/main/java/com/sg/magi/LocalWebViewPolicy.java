package com.sg.magi;

import android.net.Uri;
import android.webkit.WebResourceResponse;

import java.io.ByteArrayInputStream;
import java.util.Collections;

/** Keep app WebViews on their authenticated loopback server, including subresources. */
final class LocalWebViewPolicy {
    private LocalWebViewPolicy() {}

    static boolean isTrusted(Uri uri, int port) {
        return uri != null && port > 0 && port <= 65535
                && "http".equals(uri.getScheme())
                && "127.0.0.1".equals(uri.getHost())
                && uri.getPort() == port
                && uri.getUserInfo() == null;
    }

    static WebResourceResponse intercept(Uri uri, int port) {
        if (isTrusted(uri, port)) return null;
        if (uri != null) {
            String scheme = uri.getScheme();
            // These do not issue network requests. WebView's URL handler deals
            // with magi: page actions; javascript: and blob: are not intercepted.
            if ("about".equals(scheme) || "data".equals(scheme)
                    || "blob".equals(scheme) || "magi".equals(scheme)) {
                return null;
            }
        }
        return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden",
                Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
    }
}
