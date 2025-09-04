# YouTube Video Downloader using pytube


# Universal YouTube Video Downloader using yt-dlp
import yt_dlp

def download_video(url, output_path='.'):
	ydl_opts = {
		'outtmpl': f'{output_path}/%(title)s.%(ext)s',
		'format': 'best',
	}
	with yt_dlp.YoutubeDL(ydl_opts) as ydl:
		try:
			print(f"Downloading: {url}")
			ydl.download([url])
			print("Download completed!")
		except Exception as e:
			print(f"Error: {e}\nPlease check the URL or try updating yt-dlp.")

if __name__ == "__main__":
	url = input("Enter YouTube video or Shorts URL: ")
	download_video(url)


