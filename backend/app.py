
from flask import Flask, request, send_file, send_from_directory, jsonify
from flask_cors import CORS
import yt_dlp
import instaloader
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='../frontend', template_folder='../frontend')
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/')
def index():
    logger.info("Serving index.html")
    return send_from_directory('../frontend', 'index.html')

@app.route('/check', methods=['POST'])
def check_media():
    url = request.form.get('url')
    logger.info(f"Received check request: URL={url}")

    if not url:
        logger.error("No URL provided in the request")
        return jsonify({"error": "No URL provided"}), 400

    # Check if URL is Instagram
    if 'instagram.com' in url:
        try:
            L = instaloader.Instaloader()
            shortcode = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
            if 'p/' in url or 'reel/' in url:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                metadata = {
                    "title": post.caption or 'Instagram Post',
                    "duration": post.video_duration if post.is_video else 0,
                    "thumbnail": post.url if not post.is_video else post.video_url,
                    "quality": "HD"
                }
                logger.info(f"Instagram metadata extracted: {metadata}")
                return jsonify(metadata)
            else:
                return jsonify({"error": "Only Instagram posts and reels are supported"}), 400
        except Exception as e:
            logger.exception(f"Error checking Instagram media: {str(e)}")
            return jsonify({"error": str(e)}), 400

    # YouTube metadata
    options = {
        'format': 'best',
        'noplaylist': True,
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            metadata = {
                "title": info.get('title', 'Unknown Title'),
                "duration": info.get('duration', 0),
                "thumbnail": info.get('thumbnail', ''),
                "quality": info.get('resolution', 'Unknown Quality'),
            }
            logger.info(f"YouTube metadata extracted: {metadata}")
            return jsonify(metadata)
    except Exception as e:
        logger.exception(f"Error checking YouTube media: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/download', methods=['POST'])
def download_video():
    url = request.form.get('url')
    format_type = request.form.get('format', 'mp4')
    
    logger.info(f"Received download request: URL={url}, Format={format_type}")

    if not url:
        logger.error("No URL provided in the request")
        return jsonify({"error": "No URL provided"}), 400

    # Instagram download
    if 'instagram.com' in url:
        try:
            L = instaloader.Instaloader()
            shortcode = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
            if 'p/' in url or 'reel/' in url:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                if post.is_video:
                    file_path = f"downloads/{post.owner_username}_{shortcode}.mp4"
                    L.download_post(post, target='downloads')
                    for file in os.listdir('downloads'):
                        if file.endswith('.mp4') and shortcode in file:
                            file_path = os.path.join('downloads', file)
                            break
                else:
                    return jsonify({"error": "Only video posts are supported"}), 400

                if not os.path.exists(file_path):
                    logger.error(f"Instagram file not found at {file_path}")
                    return jsonify({"error": "File not downloaded"}), 500

                file_size = os.path.getsize(file_path)
                logger.info(f"Instagram file size: {file_size} bytes")

                download_name = f"{post.owner_username}_{shortcode}.mp4"
                logger.info(f"Sending Instagram file: {file_path} as {download_name}")
                response = send_file(file_path, as_attachment=True, download_name=download_name)

                logger.info(f"Cleaning up: Removing {file_path}")
                os.remove(file_path)

                return response
            else:
                return jsonify({"error": "Only Instagram posts and reels are supported"}), 400
        except Exception as e:
            logger.exception(f"Error downloading Instagram media: {str(e)}")
            return jsonify({"error": str(e)}), 400

    # YouTube download
    options = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'noplaylist': True,
    }

    if format_type == 'mp4':
        options.update({
            'format': 'bestvideo[vcodec~="^h264$"][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
            'merge_output_format': 'mp4',
            'recode_video': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        })
    else:  # MP3
        options.update({
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })

    try:
        if not os.path.exists('downloads'):
            logger.info("Creating downloads directory")
            os.makedirs('downloads')

        logger.debug(f"yt-dlp options: {options}")
        with yt_dlp.YoutubeDL(options) as ydl:
            logger.info(f"Starting download for URL: {url}")
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if format_type == 'mp4' and not file_path.endswith('.mp4'):
                file_path = file_path.rsplit('.', 1)[0] + '.mp4'
            elif format_type == 'mp3':
                file_path = file_path.rsplit('.', 1)[0] + '.mp3'
            logger.info(f"Download completed. File path: {file_path}")

        if not os.path.exists(file_path):
            logger.error(f"File not found at {file_path} after download")
            return jsonify({"error": "File not downloaded"}), 500

        file_size = os.path.getsize(file_path)
        logger.info(f"File size: {file_size} bytes")

        download_name = f"{info.get('title', 'media')}.{format_type}"
        logger.info(f"Sending file: {file_path} as {download_name}")
        response = send_file(file_path, as_attachment=True, download_name=download_name)

        logger.info(f"Cleaning up: Removing {file_path}")
        os.remove(file_path)

        return response
    except Exception as e:
        logger.exception(f"Error downloading video: {str(e)}")
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    logger.info("Starting Flask app with Gunicorn")
