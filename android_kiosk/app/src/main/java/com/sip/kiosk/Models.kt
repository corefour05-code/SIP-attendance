package com.sip.kiosk

import com.google.gson.annotations.SerializedName

data class ScanResponse(
    @SerializedName("faces")
    val faces: List<FaceResult>? = null
)

data class FaceResult(
    @SerializedName("bbox")
    val bbox: List<Float>? = null, // [x1, y1, x2, y2]

    @SerializedName("status")
    val status: String? = null, // "match" or "unknown"

    @SerializedName("student_id")
    val studentId: String? = null,

    @SerializedName("name")
    val name: String? = null,

    @SerializedName("action")
    val action: String? = null, // "IN" or "OUT"

    @SerializedName("first_in")
    val firstIn: String? = null,

    @SerializedName("last_out")
    val lastOut: String? = null,

    @SerializedName("total_hours")
    val totalHours: Double? = null,

    @SerializedName("duration_str")
    val durationStr: String? = null,

    @SerializedName("message")
    val message: String? = null,

    @SerializedName("speech")
    val speech: String? = null,

    @SerializedName("already_marked")
    val alreadyMarked: Boolean? = null
)
