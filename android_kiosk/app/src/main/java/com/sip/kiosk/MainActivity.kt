package com.sip.kiosk

import android.app.AlertDialog
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.SurfaceTexture
import android.hardware.usb.UsbDevice
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.view.LayoutInflater
import android.view.TextureView
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.serenegiant.usb.USBMonitor
import com.serenegiant.usb.UVCCamera
import kotlinx.coroutines.*
import java.io.ByteArrayOutputStream
import java.text.SimpleDateFormat
import java.util.*

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener, TextureView.SurfaceTextureListener {

    private lateinit var tvClock: TextView
    private lateinit var tvCameraStatus: TextView
    private lateinit var tvStaffName: TextView
    private lateinit var tvStaffId: TextView
    private lateinit var tvFirstIn: TextView
    private lateinit var tvLastOut: TextView
    private lateinit var tvShiftHours: TextView
    private lateinit var tvPunchBadge: TextView
    private lateinit var tvMessage: TextView
    private lateinit var tvAvatar: TextView
    private lateinit var btnVoice: Button
    private lateinit var btnSettings: Button
    private lateinit var overlayView: OverlayView
    private lateinit var cameraContainer: FrameLayout

    private lateinit var prefs: SharedPreferences
    private val apiClient = ApiClient()

    private var usbMonitor: USBMonitor? = null
    private var uvcCamera: UVCCamera? = null
    private var textureView: TextureView? = null
    private var previewSurface: SurfaceTexture? = null
    private var isConnected = false

    private var tts: TextToSpeech? = null
    private var voiceEnabled = true
    private val lastAnnounced = HashMap<String, Long>()
    private val ANNOUNCE_COOLDOWN_MS = 8000L

    private var isScanning = true
    private var isBusy = false
    private var scanJob: Job? = null

    private val clockHandler = Handler(Looper.getMainLooper())
    private val clockRunnable = object : Runnable {
        override fun run() {
            val sdf = SimpleDateFormat("hh:mm:ss a", Locale.getDefault())
            tvClock.text = sdf.format(Date())
            clockHandler.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("sip_kiosk_prefs", Context.MODE_PRIVATE)

        initViews()
        initCamera()
        initTTS()

        clockHandler.post(clockRunnable)
        startScanLoop()
    }

    private fun initViews() {
        tvClock = findViewById(R.id.tvClock)
        tvCameraStatus = findViewById(R.id.tvCameraStatus)
        tvStaffName = findViewById(R.id.tvStaffName)
        tvStaffId = findViewById(R.id.tvStaffId)
        tvFirstIn = findViewById(R.id.tvFirstIn)
        tvLastOut = findViewById(R.id.tvLastOut)
        tvShiftHours = findViewById(R.id.tvShiftHours)
        tvPunchBadge = findViewById(R.id.tvPunchBadge)
        tvMessage = findViewById(R.id.tvMessage)
        tvAvatar = findViewById(R.id.tvAvatar)
        btnVoice = findViewById(R.id.btnVoice)
        btnSettings = findViewById(R.id.btnSettings)
        overlayView = findViewById(R.id.overlayView)
        cameraContainer = findViewById(R.id.cameraContainer)

        val serverUrl = getServerUrl()
        if (serverUrl.isEmpty()) {
            showSettingsDialog()
        }

        btnSettings.setOnClickListener {
            showSettingsDialog()
        }

        btnVoice.setOnClickListener {
            voiceEnabled = !voiceEnabled
            btnVoice.text = if (voiceEnabled) "Voice: ON" else "Voice: OFF"
            if (!voiceEnabled) tts?.stop()
        }
    }

    private fun initCamera() {
        textureView = TextureView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            surfaceTextureListener = this@MainActivity
        }
        cameraContainer.addView(textureView, 0)

        usbMonitor = USBMonitor(this, object : USBMonitor.OnDeviceConnectListener {
            override fun onAttach(device: UsbDevice?) {
                runOnUiThread {
                    tvCameraStatus.text = "USB Camera Detected • Requesting Permission…"
                }
                device?.let { usbMonitor?.requestPermission(it) }
            }

            override fun onDettach(device: UsbDevice?) {
                runOnUiThread {
                    tvCameraStatus.text = "USB Camera Disconnected"
                    overlayView.clearFaces()
                }
                isConnected = false
                releaseCamera()
            }

            override fun onConnect(
                device: UsbDevice?,
                ctrlBlock: USBMonitor.UsbControlBlock?,
                createNew: Boolean
            ) {
                if (ctrlBlock == null) return
                try {
                    val camera = UVCCamera()
                    camera.open(ctrlBlock)
                    try {
                        camera.setPreviewSize(1280, 720, UVCCamera.FRAME_FORMAT_MJPEG)
                    } catch (e: Exception) {
                        try {
                            camera.setPreviewSize(1280, 720, UVCCamera.FRAME_FORMAT_YUYV)
                        } catch (e2: Exception) {
                            camera.setPreviewSize(640, 480, UVCCamera.FRAME_FORMAT_MJPEG)
                        }
                    }

                    previewSurface?.let { st ->
                        camera.setPreviewTexture(st)
                        camera.startPreview()
                    }

                    uvcCamera = camera
                    isConnected = true

                    runOnUiThread {
                        tvCameraStatus.text = getString(R.string.camera_ready)
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                    runOnUiThread {
                        tvCameraStatus.text = "Camera Error: ${e.message}"
                    }
                }
            }

            override fun onDisconnect(
                device: UsbDevice?,
                ctrlBlock: USBMonitor.UsbControlBlock?
            ) {
                isConnected = false
                runOnUiThread {
                    tvCameraStatus.text = "USB Disconnected"
                }
                releaseCamera()
            }

            override fun onCancel(device: UsbDevice?) {
                runOnUiThread {
                    tvCameraStatus.text = "USB Permission Denied"
                }
            }
        })
    }

    override fun onStart() {
        super.onStart()
        usbMonitor?.register()
    }

    override fun onStop() {
        super.onStop()
        usbMonitor?.unregister()
    }

    override fun onSurfaceTextureAvailable(surface: SurfaceTexture, width: Int, height: Int) {
        previewSurface = surface
        uvcCamera?.let { camera ->
            try {
                camera.setPreviewTexture(surface)
                camera.startPreview()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    override fun onSurfaceTextureSizeChanged(surface: SurfaceTexture, width: Int, height: Int) {}

    override fun onSurfaceTextureDestroyed(surface: SurfaceTexture): Boolean {
        previewSurface = null
        try {
            uvcCamera?.stopPreview()
        } catch (e: Exception) {}
        return true
    }

    override fun onSurfaceTextureUpdated(surface: SurfaceTexture) {}

    private fun releaseCamera() {
        try {
            uvcCamera?.stopPreview()
            uvcCamera?.close()
            uvcCamera?.destroy()
        } catch (e: Exception) {
            e.printStackTrace()
        }
        uvcCamera = null
    }

    private fun startScanLoop() {
        scanJob?.cancel()
        scanJob = lifecycleScope.launch(Dispatchers.Default) {
            while (isActive) {
                if (!isScanning || isBusy || !isConnected) {
                    delay(200)
                    continue
                }

                val currentTexture = textureView
                val serverUrl = getServerUrl()
                if (currentTexture == null || !currentTexture.isAvailable || serverUrl.isEmpty()) {
                    delay(300)
                    continue
                }

                try {
                    val bitmap = withContext(Dispatchers.Main) {
                        currentTexture.bitmap
                    }

                    if (bitmap != null) {
                        isBusy = true
                        val baos = ByteArrayOutputStream()
                        bitmap.compress(Bitmap.CompressFormat.JPEG, 80, baos)
                        val jpegBytes = baos.toByteArray()
                        baos.close()

                        val response = apiClient.scanFrame(serverUrl, jpegBytes)
                        withContext(Dispatchers.Main) {
                            handleScanResponse(response, bitmap.width, bitmap.height)
                        }
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                } finally {
                    isBusy = false
                }

                delay(150)
            }
        }
    }

    private fun handleScanResponse(response: ScanResponse?, frameWidth: Int, frameHeight: Int) {
        val faces = response?.faces
        if (faces.isNullOrEmpty()) {
            overlayView.clearFaces()
            return
        }

        overlayView.updateFaces(faces, frameWidth, frameHeight)

        val match = faces.firstOrNull { it.status == "match" }
        if (match != null) {
            tvStaffName.text = match.name ?: "Unknown Staff"
            tvStaffId.text = match.studentId ?: ""
            tvAvatar.text = (match.name?.firstOrNull()?.toString() ?: "👤").uppercase()

            if (match.action == "IN") {
                tvPunchBadge.text = "● Morning Clock IN"
                tvPunchBadge.setBackgroundResource(R.drawable.gold_button)
            } else {
                tvPunchBadge.text = "🔄 Shift Updated"
                tvPunchBadge.setBackgroundResource(R.drawable.rounded_card)
            }

            tvFirstIn.text = match.firstIn ?: "--:--"
            tvLastOut.text = match.lastOut ?: "--:--"
            tvShiftHours.text = match.durationStr ?: "0h 0m"
            tvMessage.text = match.message ?: "Shift logged successfully."

            val staffId = match.studentId ?: ""
            val now = System.currentTimeMillis()
            val lastTime = lastAnnounced[staffId] ?: 0L
            if (now - lastTime > ANNOUNCE_COOLDOWN_MS) {
                lastAnnounced[staffId] = now
                speak(match.speech ?: "Welcome ${match.name}")
            }
        } else {
            tvStaffName.text = "Unrecognized Face"
            tvStaffId.text = "Not in roster"
            tvAvatar.text = "?"
            tvPunchBadge.text = "Unknown"
            tvMessage.text = "Please register staff at enrollment desk."
        }
    }

    private fun initTTS() {
        tts = TextToSpeech(this, this)
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            tts?.language = Locale.US
            tts?.setSpeechRate(1.02f)
        }
    }

    private fun speak(text: String) {
        if (!voiceEnabled || text.isBlank()) return
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "KioskScan")
    }

    private fun getServerUrl(): String {
        return prefs.getString("server_url", "") ?: ""
    }

    private fun showSettingsDialog() {
        val view = LayoutInflater.from(this).inflate(R.layout.dialog_settings, null)
        val etUrl = view.findViewById<EditText>(R.id.etServerUrl)
        etUrl.setText(getServerUrl())

        AlertDialog.Builder(this)
            .setView(view)
            .setPositiveButton("Save & Connect") { _, _ ->
                val newUrl = etUrl.text.toString().trim()
                if (newUrl.isNotEmpty()) {
                    prefs.edit().putString("server_url", newUrl).apply()
                    Toast.makeText(this, "Server URL Saved!", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        clockHandler.removeCallbacks(clockRunnable)
        scanJob?.cancel()
        tts?.shutdown()
        releaseCamera()
        usbMonitor?.destroy()
    }
}
