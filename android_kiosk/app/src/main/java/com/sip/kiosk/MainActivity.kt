package com.sip.kiosk

import android.app.AlertDialog
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.hardware.usb.UsbDevice
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.view.LayoutInflater
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
import com.jiangdg.usbcamera.UVCCameraHelper
import com.serenegiant.usb.widget.CameraViewInterface
import com.serenegiant.usb.widget.UVCCameraTextureView
import kotlinx.coroutines.*
import java.io.ByteArrayOutputStream
import java.text.SimpleDateFormat
import java.util.*

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener, CameraViewInterface.Callback {

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

    private var cameraHelper: UVCCameraHelper? = null
    private var uvcView: UVCCameraTextureView? = null
    private var isRequest = false
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
        uvcView = UVCCameraTextureView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            setCallback(this@MainActivity)
        }
        cameraContainer.addView(uvcView, 0)

        cameraHelper = UVCCameraHelper.getInstance().apply {
            setDefaultPreviewSize(1280, 720)
            setDefaultFrameFormat(UVCCameraHelper.FRAME_FORMAT_MJPEG)
            initUSBMonitor(this@MainActivity, uvcView, object : UVCCameraHelper.OnMyDevConnectListener {
                override fun onAttachDevice(device: UsbDevice?) {
                    runOnUiThread {
                        tvCameraStatus.text = "USB Camera Detected • Requesting Permission…"
                    }
                    if (!isRequest) {
                        isRequest = true
                        requestPermission(device)
                    }
                }

                override fun onDettachDevice(device: UsbDevice?) {
                    runOnUiThread {
                        tvCameraStatus.text = "USB Camera Disconnected"
                        overlayView.clearFaces()
                    }
                    isRequest = false
                    isConnected = false
                }

                override fun onConnectDev(device: UsbDevice?, isConn: Boolean) {
                    isConnected = isConn
                    runOnUiThread {
                        if (isConn) {
                            tvCameraStatus.text = getString(R.string.camera_ready)
                            openCamera()
                        }
                    }
                }

                override fun onDisConnectDev(device: UsbDevice?) {
                    isConnected = false
                    runOnUiThread {
                        tvCameraStatus.text = "USB Disconnected"
                    }
                }

                override fun onCancelPermit(device: UsbDevice?) {
                    runOnUiThread {
                        tvCameraStatus.text = "USB Permission Denied"
                    }
                }
            })
        }
    }

    override fun onStart() {
        super.onStart()
        cameraHelper?.registerUSB()
    }

    override fun onStop() {
        super.onStop()
        cameraHelper?.unregisterUSB()
    }

    override fun onSurfaceCreated(view: CameraViewInterface?, surface: android.view.Surface?) {
        if (!isRequest && cameraHelper?.isCameraOpened == false) {
            cameraHelper?.selectDevice()
        }
    }

    override fun onSurfaceChanged(view: CameraViewInterface?, surface: android.view.Surface?, width: Int, height: Int) {}

    override fun onSurfaceDestroy(view: CameraViewInterface?, surface: android.view.Surface?) {
        if (cameraHelper?.isCameraOpened == true) {
            cameraHelper?.closeCamera()
        }
    }

    private fun startScanLoop() {
        scanJob?.cancel()
        scanJob = lifecycleScope.launch(Dispatchers.Default) {
            while (isActive) {
                if (!isScanning || isBusy || !isConnected) {
                    delay(200)
                    continue
                }

                val currentTexture = uvcView
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
            tvAvatar.text = (match.name?.firstOrNull() ?: '👤').uppercase()

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
        cameraHelper?.release()
    }
}
