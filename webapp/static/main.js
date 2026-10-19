$(function () {
    'use strict';
    // Drop Zone from https://bootsnipp.com/snippets/D7MvX
    // UPLOAD CLASS DEFINITION
    // ======================

    var dropZone = document.getElementById('drop-zone');
    var uploadForm = document.getElementById('js-upload-form');

    var startUpload = function () {
        $('#js-upload-submit').prop('disabled', true)
        $('#upload-status').removeClass('d-none')
        console.log($('#js-upload-form')[0])
        let formData = new FormData($('#js-upload-form')[0]);
        $.ajax({
            type: "POST",
            url: "/midi-info",
            enctype: 'multipart/form-data',
            data: formData,
            contentType: false,
            cache: false,
            processData: false,
            success: function (response) {
                var obj = JSON.parse(response);
                $('#score-view').text('')
                var osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay("score-view");
                window.musicXml = obj.musicxml
                // OSMD >= 2.0: load() returns a Promise
                osmd.load(obj.musicxml).then(function () {
                    osmd.render();
                }).catch(function (error) {
                    console.error("Score rendering failed:", error);
                    $('#js-upload-submit').prop('disabled', false)
                });
                $('#midi-track-list').text('')
                var i;
                for (i = 0; i < obj.parts.length; i++) {
                    $('#midi-track-list').append(
                        '<li class="list-group-item" draggable="true" ondragstart="drag(event)" id="' +
                        obj.parts[i] + '">Track ' + (i + 1) + ' (' + obj.parts[i] + ')' +
                        '<input type="hidden" name="trackId" value="' + i + '"></li>');
                }
            },
            error: function (data) {
                $('#js-upload-submit').prop('disabled', false)
                $('#upload-status').addClass('d-none')
            }
        });
    }

    uploadForm.addEventListener('submit', function (event) {
        var uploadFiles = document.getElementById('js-upload-files').files;
        event.preventDefault()

        startUpload()
    })

    dropZone.ondrop = function (event) {
        event.preventDefault();
        this.className = 'upload-drop-zone';
        document.getElementById('js-upload-files').files = event.dataTransfer.files

        startUpload()
    }

    dropZone.ondragover = function () {
        this.className = 'upload-drop-zone drop';
        return false;
    }

    dropZone.ondragleave = function () {
        this.className = 'upload-drop-zone';
        return false;
    }

    $('#voice-margin').on('input', function () {
        $('#voice-margin-value').text(this.value + ' dB')
    })

    $('#accompaniment-volume').on('input', function () {
        $('#accompaniment-volume-value').text(decibelText(this.value))
    })

    $('#btDownload').click(function () {
        $(this).prop('disabled', true);
        $('#errorMessage').text('')

        let downloadFormData = new FormData();
        $("#soprano-tracks :input").each(function (i, val) { downloadFormData.append('soprano', val.value) })
        $("#alto-tracks :input").each(function (i, val) { downloadFormData.append('alto', val.value) })
        $("#tenor-tracks :input").each(function (i, val) { downloadFormData.append('tenor', val.value) })
        $("#bass-tracks :input").each(function (i, val) { downloadFormData.append('bass', val.value) })
        $("#accompaniment-tracks :input").each(function (i, val) { downloadFormData.append('accompaniment', val.value) })
        downloadFormData.append('voice_margin', $('#voice-margin').val())
        downloadFormData.append('accompaniment_volume', $('#accompaniment-volume').val())
        if ($('#instrument-selector option:selected').val() != '-1') {
            downloadFormData.append('instrument', $('#instrument-selector option:selected').val())
        }
        downloadFormData.append('musicxml', window.musicXml)
        showProgress(0, 'Starting the conversion…')
        $.ajax(
            {
                type: "POST",
                url: 'jobs',
                data: downloadFormData,
                enctype: 'multipart/form-data',
                contentType: false,
                cache: false,
                processData: false,
                success: function (data) {
                    pollJob(data.id)
                },
                error: function (jqXHR, textStatus) {
                    jobFailed("The conversion could not be started (HTTP error code " + jqXHR.status + ", text status '" + textStatus + "')")
                }
            }
        );
    });
});

// Asks the server every second how far the conversion is and starts the
// download as soon as it is finished
function pollJob(jobId) {
    $.ajax({
        url: 'jobs/' + jobId,
        cache: false,
        success: function (job) {
            if (job.status === 'done') {
                showProgress(100, 'Done, the download starts.')
                window.location.href = 'jobs/' + jobId + '/download'
                $('#btDownload').prop('disabled', false);
            } else if (job.status === 'failed') {
                jobFailed('The conversion failed. Please check the voice assignment and try again.')
            } else {
                if (job.status === 'queued') {
                    showProgress(0, 'Waiting for other conversions to finish…')
                } else {
                    showProgress(job.percent, remainingText(job.remaining_s))
                }
                setTimeout(function () { pollJob(jobId) }, 1000)
            }
        },
        error: function (jqXHR, textStatus) {
            jobFailed("The progress could not be read (HTTP error code " + jqXHR.status + ", text status '" + textStatus + "')")
        }
    });
}

function remainingText(seconds) {
    if (seconds === null) {
        return 'Preparing the score…'
    }
    if (seconds < 60) {
        return 'About ' + seconds + ' seconds left'
    }
    let minutes = Math.round(seconds / 60)
    return 'About ' + minutes + (minutes === 1 ? ' minute' : ' minutes') + ' left'
}

function decibelText(value) {
    return (value > 0 ? '+' : '') + value + ' dB'
}

function showProgress(percent, text) {
    $('#job-progress').removeClass('d-none').attr('aria-valuenow', percent)
    $('#job-progress .progress-bar').css('width', percent + '%')
    $('#job-status').text(text)
}

function jobFailed(message) {
    $('#job-progress').addClass('d-none')
    $('#job-status').text('')
    $('#errorMessage').text(message)
    $('#btDownload').prop('disabled', false);
}

function allowDrop(event) {
    event.preventDefault();
}

function drag(event) {
    event.dataTransfer.setData("text", event.target.id);
}

function drop(event) {
    event.preventDefault();
    let data = event.dataTransfer.getData("text");
    event.target.appendChild(document.getElementById(data));
    // the accompaniment volume only matters once a track is in Accompaniment
    $('#accompaniment-volume-setting').toggleClass('d-none', $('#accompaniment-tracks li').length === 0)
}