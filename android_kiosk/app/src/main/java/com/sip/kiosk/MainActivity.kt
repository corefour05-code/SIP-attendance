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
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.jiangdg.ausbc.CameraClient
import com.jiangdg.ausbc.callback.ICameraStateCallBack
import com.jiangdg.ausbc.callback.IDeviceConnectCallBack
import com.jiangdg.ausbc.camera.bean.CameraRequest
import com.jiangdg.ausbc.widget.AspectRatioTextureView
import com.sip.kiosk.databinding.ActivityMainBinding
import kotlinx.coroutines.*
import java.io.ByteArrayOutputStream
import java.text.SimpleDateFormat
import java.util.*

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: SharedPreferences
    private val apiClient = ApiClient()

    private var cameraClient: CameraClient? = null
    private var textureView: AspectRatioTextureView? = null

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
            binding.tvClock.text = sdf.format(Date())
            clockHandler.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = getSharedPreferences("sip_kiosk_prefs", Context.MODE_PRIVATE)

        initViews()
        initCamera()
        initTTS()

        clockHandler.post(clockRunnable)
        startScanLoop()
    }

    private fun initViews() {
        val serverUrl = getServerUrl()
        if (serverUrl.isEmpty()) {
            showSettingsDialog()
        }

        binding.btnSettings.setOnClickListener {
            showSettingsDialog()
        }

        binding.btnVoice.setOnClickListener {
            voiceEnabled = !voiceEnabled
            binding.btnVoice.text = if (voiceEnabled) "Voice: ON" else "Voice: OFF"
            if (!voiceEnabled) tts?.stop()
        }
    }

    private fun initCamera() {
        // Create AspectRatioTextureView dynamically for USB camera rendering
        textureView = AspectRatioTextureView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            setAspectRatio(1280, 720)
        }
        binding.cameraContainer.addView(textureView, 0)

        // Initialize USB Camera Client
        cameraClient = CameraClient.newBuilder(this)
            .setEnableGpu(false)
            .setRawImage(false)
            .openDebug(true)
            .setCameraStrategy(CameraClient.CameraStrategy.UVC)
            .setCameraRequest(
                CameraRequest.Builder()
                    .setPreviewWidth(1280)
                    .setPreviewHeight(720)
                    .setRenderMode(CameraRequest.RenderMode.FIT_XY)
                    .create()
            )
            .build()

        cameraClient?.apply {
            // Set USB device lifecycle callbacks
            registerDeviceConnectCallBack(object : IDeviceConnectCallBack {
                override fun onAttachDev(device: UsbDevice?) {
                    runOnUiThread {
                        binding.tvCameraStatus.text = "USB Camera Detected • Requesting Permission…"
                        binding.tvCameraStatus.setBackgroundResource(R.drawable.rounded_card)
                    }
                }

                override fun onDetachDev(device: UsbDevice?) {
                    runOnUiThread {
                        binding.tvCameraStatus.text = "USB Camera Disconnected"
                        binding.overlayView.clearFaces()
                    }
                }

                override fun onConnectDev(device: UsbDevice?, isConnect: Boolean) {
                    if (isConnect) {
                        runOnUiThread {
                            binding.tvCameraStatus.text = getString(R.string.camera_ready)
                        }
                    }
                }

                override fun onDisConnectDev(device: UsbDevice?) {
                    runOnUiThread {
                        binding.tvCameraStatus.text = "USB Disconnected"
                    }
                }
            })

            // Camera preview state callback
            registerCameraStateCallBack(object : ICameraStateCallBack {
                override fun onCameraState(
                    self: ICameraStateCallBack.State,
                    msg: String?
                ) {
                    runOnUiThread {
                        when (self) {
                            ICameraStateCallBack.State.OPENED -> {
                                binding.tvCameraStatus.text = getString(R.string.camera_ready)
                            }
                            ICameraStateCallBack.State.CLOSED -> {
                                binding.tvCameraStatus.text = "Camera Closed"
                            }
                            ICameraStateCallBack.State.ERROR -> {
                                binding.tvCameraStatus.text = "Camera Error: $msg"
                            }
                        }
                    }
                }
            })
        }

        textureView?.let { tv ->
            cameraClient?.openCamera(tv)
        }
    }

    private fun startScanLoop() {
        scanJob?.cancel()
        scanJob = lifecycleScope.launch(Dispatchers.Default) {
            while (isActive) {
                if (!isScanning || isBusy) {
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
                    // Capture current frame bitmap from TextureView
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

                delay(150) // Gap between scan calls
            }
        }
    }

    private fun handleScanResponse(response: ScanResponse?, frameWidth: Int, frameHeight: Int) {
        val faces = response?.faces
        if (faces.isNullOrEmpty()) {
            binding.overlayView.clearFaces()
            return
        }

        // Draw bounding boxes on custom overlay view
        binding.overlayView.updateFaces(faces, frameWidth, frameHeight)

        // Find first matched face
        val match = faces.firstOrNull { it.status == "match" }
        if (match != null) {
            binding.tvStaffName.text = match.name ?: "Unknown Staff"
            binding.tvStaffId.text = match.studentId ?: ""
            binding.tvAvatar.text = (match.name?.firstOrNull() ?: '👤').uppercase()

            if (match.action == "IN") {
                binding.tvPunchBadge.text = "● Morning Clock IN"
                binding.tvPunchBadge.setBackgroundResource(R.drawable.gold_button)
            } else {
                binding.tvPunchBadge.text = "🔄 Shift Updated"
                binding.tvPunchBadge.setBackgroundResource(R.drawable.rounded_card)
            }

            binding.tvFirstIn.text = match.firstIn ?: "--:--"
            binding.tvLastOut.text = match.lastOut ?: "--:--"
            binding.tvShiftHours.text = match.durationStr ?: "0h 0m"
            binding.tvMessage.text = match.message ?: "Shift logged successfully."

            // Announce voice greeting
            val staffId = match.studentId ?: ""
            val now = System.currentTimeMillis()
            val lastTime = lastAnnounced[staffId] ?: 0L
            if (now - lastTime > ANNOUNCE_COOLDOWN_MS) {
                lastAnnounced[staffId] = now
                speak(match.speech ?: "Welcome ${match.name}")
            }
        } else {
            binding.tvStaffName.text = "Unrecognized Face"
            binding.tvStaffId.text = "Not in roster"
            binding.tvAvatar.text = "?"
            binding.tvPunchBadge.text = "Unknown"
            binding.tvMessage.text = "Please register staff at enrollment desk."
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
        cameraClient?.closeCamera()
    }
}
