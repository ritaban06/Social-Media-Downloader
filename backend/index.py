from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import instaloader
import logging
import tempfile
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/')
def index():
    return jsonify({
        "message": "Media Downloader API",
        "status": "running",
        "endpoints": [
            "/check - Check media metadata",
            "/download - Download media"
        ]
    })

@app.route('/check', methods=['POST'])
def check_media():
    url = request.form.get('url')
    logger.info(f"Received check request: URL={url}")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        # Instagram metadata
        if 'instagram.com' in url:
            L = instaloader.Instaloader()
            shortcode = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
            
            if 'p/' in url or 'reel/' in url:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                metadata = {
                    "platform": "Instagram",
                    "title": post.caption or 'Instagram Post',
                    "duration": post.video_duration if post.is_video else 0,
                    "thumbnail": post.url if not post.is_video else post.video_url,
                    "quality": "HD",
                    "is_video": post.is_video
                }
                return jsonify(metadata)
            
            return jsonify({"error": "Only Instagram posts and reels are supported"}), 400

        # YouTube metadata
        options = {
            'format': 'best',
            'noplaylist': True,
            'quiet': True
        }
        
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            metadata = {
                "platform": "YouTube",
                "title": info.get('title', 'Unknown Title'),
                "duration": info.get('duration', 0),
                "thumbnail": info.get('thumbnail', ''),
                "quality": info.get('resolution', 'Unknown Quality'),
                "is_video": True
            }
            return jsonify(metadata)

    except Exception as e:
        logger.error(f"Metadata extraction error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/download', methods=['POST'])
def download_video():
    url = request.form.get('url')
    format_type = request.form.get('format', 'mp4')
    
    logger.info(f"Received download request: URL={url}, Format={format_type}")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        # Temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            # Instagram download
            if 'instagram.com' in url:
                L = instaloader.Instaloader()
                shortcode = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                
                if 'p/' in url or 'reel/' in url:
                    post = instaloader.Post.from_shortcode(L.context, shortcode)
                    
                    if post.is_video:
                        file_path = os.path.join(temp_dir, f"{post.owner_username}_{shortcode}.mp4")
                        L.download_post(post, target=temp_dir)
                        
                        # Find the video file
                        for file in os.listdir(temp_dir):
                            if file.endswith('.mp4') and shortcode in file:
                                file_path = os.path.join(temp_dir, file)
                                break
                    else:
                        return jsonify({"error": "Only video posts are supported"}), 400

                    # In serverless, we'll return file contents
                    with open(file_path, 'rb') as f:
                        file_contents = f.read()
                    
                    return jsonify({
                        "filename": f"{post.owner_username}_{shortcode}.mp4",
                        "content": file_contents.hex()  # Convert to hex for transmission
                    })

            # YouTube download
            options = {
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'noplaylist': True,
            }

            if format_type == 'mp4':
                options.update({
                    'format': 'bestvideo[vcodec~="^h264$"][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                    'merge_output_format': 'mp4',
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

            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                
                # Ensure correct file extension
                if format_type == 'mp4' and not file_path.endswith('.mp4'):
                    file_path = file_path.rsplit('.', 1)[0] + '.mp4'
                elif format_type == 'mp3':
                    file_path = file_path.rsplit('.', 1)[0] + '.mp3'

                # Read file contents
                with open(file_path, 'rb') as f:
                    file_contents = f.read()
                
                return jsonify({
                    "filename": f"{info.get('title', 'media')}.{format_type}",
                    "content": file_contents.hex()  # Convert to hex for transmission
                })

    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def handler(event, context):
    return app