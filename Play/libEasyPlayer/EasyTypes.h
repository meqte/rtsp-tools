
#ifndef __RTSP_TYPES_H__
#define __RTSP_TYPES_H__

#ifdef _WIN32
#define LIB_LIVEPLAYER_API  __declspec(dllexport)
#ifndef LIB_APICALL
#define LIB_APICALL  __stdcall
#endif
#define WIN32_LEAN_AND_MEAN
#else
#define LIB_LIVEPLAYER_API
#define LIB_APICALL 
#endif



//ý������
#ifndef MEDIA_TYPE_VIDEO
#define MEDIA_TYPE_VIDEO		0x00000001
#endif
#ifndef MEDIA_TYPE_AUDIO
#define MEDIA_TYPE_AUDIO		0x00000002
#endif
#ifndef MEDIA_TYPE_EVENT
#define MEDIA_TYPE_EVENT		0x00000004
#endif
#ifndef MEDIA_TYPE_RTP
#define MEDIA_TYPE_RTP			0x00000008
#endif
#ifndef MEDIA_TYPE_SDP
#define MEDIA_TYPE_SDP			0x00000010
#endif
#ifndef MEDIA_TYPE_CODEC_INFO
#define	MEDIA_TYPE_CODEC_INFO	0x00000020
#endif


typedef enum __RTSP_SERVER_ERROR_CODE_ENUM
{
	RTSP_SERVER_ERR_NoErr			=	0,
	RTSP_SERVER_ERR_NotInitialized	=	-1,			//û�г�ʼ��
	RTSP_SERVER_ERR_BadArgument		=	-2,			//��������
	RTSP_SERVER_ERR_ALLOC_MEMORY	=	-3,			//�ڴ����ʧ��
	RTSP_SERVER_ERR_OPERATE			=	-4,			//����ʧ��
}RTSP_SERVER_ERROR_CODE_ENUM;


//��Ƶ����
#define RTSP_VIDEO_CODEC_H264	0x1C				//H264
#define RTSP_VIDEO_CODEC_H265	0xAE				//H265		174
#define	RTSP_VIDEO_CODEC_MJPEG	0x08				//MJPEG
#define	RTSP_VIDEO_CODEC_MPEG4	0x0D				//MPEG4

//��Ƶ����
#define RTSP_AUDIO_CODEC_AAC	0x15002		//AAC
#define RTSP_AUDIO_CODEC_G711U	0x10006		//G711 ulaw
#define RTSP_AUDIO_CODEC_G711A	0x10007		// G711 alaw
#define RTSP_AUDIO_CODEC_G726	0x1100B		//G726


//��Ƶ�ؼ��ֱ�ʶ
//#define RTSP_VIDEO_FRAME_I		0x01		//I֡
#define LIVE_FRAME_TYPE_I		0x01		//I֡
#define LIVE_FRAME_TYPE_P		0x02		//P֡
#define LIVE_FRAME_TYPE_B		0x03		//B֡
#define LIVE_FRAME_TYPE_J		0x04		//JPEG

//ý����Ϣ
typedef struct __LIVE_MEDIA_INFO_T
{
	unsigned int videoCodec;			//��Ƶ��������
	unsigned int videoFps;				//��Ƶ֡��
	int			 videoWidth;
	int			 videoHeight;
	float		 videoBitrate;

	unsigned int audioCodec;			//��Ƶ��������
	unsigned int audioSampleRate;		//��Ƶ������
	unsigned int audioChannel;			//��Ƶͨ����
	unsigned int audioBitsPerSample;	//��Ƶ��������

	unsigned int metadataCodec;			//Metadata����

	unsigned int vpsLength;				//��Ƶvps֡����
	unsigned int spsLength;				//��Ƶsps֡����
	unsigned int ppsLength;				//��Ƶpps֡����
	unsigned int seiLength;				//��Ƶsei֡����
	unsigned char	 vps[255];			//��Ƶvps֡����
	unsigned char	 sps[255];			//��Ƶsps֡����
	unsigned char	 pps[128];			//��Ƶsps֡����
	unsigned char	 sei[128];			//��Ƶsei֡����
}LIVE_MEDIA_INFO_T;




#endif
