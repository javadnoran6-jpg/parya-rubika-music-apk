package ir.parya.rubikabot;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {

    private static final String PREFS_NAME = "parya_rubika_prefs";
    private static final String KEY_SERVER_URL = "server_url";
    private static final String TERMUX_LOCAL_URL = "http://127.0.0.1:3000";
    private static final String DEFAULT_ONLINE_URL = "http://127.0.0.1:3000";

    private WebView webView;
    private TextView statusText;
    private SharedPreferences prefs;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#0B0F17"));

        // Compact Top Switcher Bar (Termux Local vs Online Studio)
        LinearLayout topBar = new LinearLayout(this);
        topBar.setOrientation(LinearLayout.HORIZONTAL);
        topBar.setBackgroundColor(Color.parseColor("#111827"));
        topBar.setPadding(16, 12, 16, 12);
        topBar.setGravity(Gravity.CENTER_VERTICAL);

        statusText = new TextView(this);
        statusText.setText("Parya Rubika");
        statusText.setTextColor(Color.parseColor("#34D399"));
        statusText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        LinearLayout.LayoutParams titleLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        topBar.addView(statusText, titleLp);

        Button btnTermux = makeBarButton("Termux 3000", "#059669");
        btnTermux.setOnClickListener(v -> loadTarget(TERMUX_LOCAL_URL, "Termux Local"));
        topBar.addView(btnTermux);

        Button btnOnline = makeBarButton("Online Panel", "#1E293B");
        btnOnline.setOnClickListener(v -> loadTarget(DEFAULT_ONLINE_URL, "Online Panel"));
        topBar.addView(btnOnline);

        Button btnUrl = makeBarButton("URL", "#1E293B");
        btnUrl.setOnClickListener(v -> promptCustomUrl());
        topBar.addView(btnUrl);

        Button btnHide = makeBarButton("X", "#334155");
        btnHide.setOnClickListener(v -> topBar.setVisibility(View.GONE));
        topBar.addView(btnHide);

        root.addView(topBar, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));

        webView = new WebView(this);
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        ws.setAllowFileAccess(true);
        ws.setUserAgentString(ws.getUserAgentString() + " ParyaRubikaAPK/1.0");

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    showOfflineTermuxGuide(String.valueOf(request.getUrl()));
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> request.grant(request.getResources()));
            }
        });

        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            try {
                if (url.startsWith("http")) {
                    DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                    req.setMimeType(mimeType);
                    req.setTitle(URLUtil.guessFileName(url, contentDisposition, mimeType));
                    req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,
                            URLUtil.guessFileName(url, contentDisposition, mimeType));
                    DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
                    if (dm != null) {
                        dm.enqueue(req);
                        Toast.makeText(MainActivity.this, "Downloading to Downloads...", Toast.LENGTH_SHORT).show();
                    }
                }
            } catch (Exception ignored) {
            }
        });

        root.addView(webView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(root);

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1001);
        }

        autoDetectAndLoad();
    }

    private Button makeBarButton(String label, String hexBg) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        b.setBackgroundColor(Color.parseColor(hexBg));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.setMarginStart(8);
        b.setLayoutParams(lp);
        b.setPadding(18, 6, 18, 6);
        b.setMinHeight(0);
        b.setMinimumHeight(0);
        return b;
    }

    private void autoDetectAndLoad() {
        String saved = prefs.getString(KEY_SERVER_URL, "");
        if (!saved.isEmpty()) {
            loadTarget(saved, saved.contains("127.0.0.1") ? "Termux Local" : "Saved Server");
            return;
        }
        statusText.setText("Checking Termux...");
        new Thread(() -> {
            boolean termuxAlive = isUrlReachable(TERMUX_LOCAL_URL + "/api/state");
            runOnUiThread(() -> {
                if (termuxAlive) {
                    loadTarget(TERMUX_LOCAL_URL, "Termux Local");
                } else if (!DEFAULT_ONLINE_URL.isEmpty() && !DEFAULT_ONLINE_URL.contains("127.0.0.1")) {
                    loadTarget(DEFAULT_ONLINE_URL, "Online Panel");
                } else {
                    loadTarget(TERMUX_LOCAL_URL, "Termux Local");
                }
            });
        }).start();
    }

    private boolean isUrlReachable(String target) {
        try {
            HttpURLConnection conn = (HttpURLConnection) new URL(target).openConnection();
            conn.setConnectTimeout(1200);
            conn.setReadTimeout(1200);
            conn.setRequestMethod("GET");
            return conn.getResponseCode() >= 200 && conn.getResponseCode() < 500;
        } catch (Exception e) {
            return false;
        }
    }

    private void loadTarget(String url, String label) {
        prefs.edit().putString(KEY_SERVER_URL, url).apply();
        statusText.setText(label);
        webView.loadUrl(url);
    }

    private void promptCustomUrl() {
        EditText input = new EditText(this);
        input.setText(prefs.getString(KEY_SERVER_URL, TERMUX_LOCAL_URL));
        new AlertDialog.Builder(this)
                .setTitle("آدرس سرور ترموکس یا پنل")
                .setView(input)
                .setPositiveButton("اتصال", (d, w) -> {
                    String val = input.getText().toString().trim();
                    if (!val.isEmpty()) {
                        loadTarget(val, "Custom URL");
                    }
                })
                .setNegativeButton("لغو", null)
                .show();
    }

    private void showOfflineTermuxGuide(String failedUrl) {
        String html = "<html lang='fa' dir='rtl'><body style='background:#0B0F17;color:#E2E8F0;font-family:sans-serif;padding:24px'>"
                + "<h2 style='color:#34D399'>سرور ترموکس هنوز روشن نیست</h2>"
                + "<p style='font-size:13px;color:#94A3B8'>آدرس فعلی در دسترس نبود: <code dir='ltr'>" + failedUrl + "</code></p>"
                + "<div style='background:#111827;border:1px solid #1E293B;border-radius:12px;padding:16px;margin-top:16px'>"
                + "<p style='font-size:13px;margin:0 0 8px'>۱. برنامه <b>Termux</b> را باز کنید و این دستور را بزنید:</p>"
                + "<pre dir='ltr' style='background:#0B0F17;padding:10px;border-radius:8px;color:#34D399;overflow:auto;font-size:11px'>"
                + "cd ~/parya-rubika-bot &amp;&amp; bash termux/setup.sh</pre>"
                + "<p style='font-size:13px;margin:8px 0 0'>۲. گزینه <b>1 (Run Bot + Local APK Server)</b> را انتخاب کنید و سپس دکمه بالا <b>Termux 3000</b> را بزنید.</p>"
                + "</div></body></html>";
        webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
