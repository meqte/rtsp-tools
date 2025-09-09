#ifndef __LIB_EASY_PLAYER_API_H__
#define __LIB_EASY_PLAYER_API_H__

#ifdef _DEBUG
//#include <vld.h>
#endif

#include <winsock2.h>
#include "EasyTypes.h"

typedef enum __RENDER_FORMAT
{
	RENDER_FORMAT_YV12		=		842094169,
	RENDER_FORMAT_YUY2		=		844715353,
	RENDER_FORMAT_UYVY		=		1498831189,
	RENDER_FORMAT_A8R8G8B8	=		21,
	RENDER_FORMAT_X8R8G8B8	=		22,
	RENDER_FORMAT_RGB565	=		23,
	RENDER_FORMAT_RGB555	=		25,

	RENDER_FORMAT_RGB24_GDI=		26,
	RENDER_FORMAT_RGB32_GDI=		27
}RENDER_FORMAT;

//ͨ��Դ���� (ָ��Դ����)
typedef enum __LIVE_CHANNEL_TYPE_ENUM
{
	LIVE_CHANNEL_SOURCE_TYPE_RTSP	=	0,		//ԴΪRTSP(����)
	LIVE_CHANNEL_SOURCE_TYPE_RTMP,				//ԴΪRTMP(����)
	LIVE_CHANNEL_SOURCE_TYPE_HLS,				//ԴΪHLS(����)
	LIVE_CHANNEL_SOURCE_TYPE_FILE,				//ԴΪ�����ļ�(����)
	LIVE_CHANNEL_SOURCE_TYPE_ENCODE_DATA,		//ԴΪ�ⲿ�ı�������
	LIVE_CHANNEL_SOURCE_TYPE_DECODE_DATA,		//ԴΪ�ⲿ�Ľ�������
}LIVE_CHANNEL_SOURCE_TYPE_ENUM;

// �����ٶ�
typedef enum __PLAY_SPEED_ENUM
{	
	PLAY_SPEED_UNKNOWN	=	-1,
	PLAY_SPEED_NORMAL	=	0x00,		// ��������
	PLAY_SPEED_PAUSED,					// ��ͣ
	PLAY_SPEED_SLOW_X2,					// 1/2
	PLAY_SPEED_SLOW_X4,					// 1/4
	PLAY_SPEED_SLOW_X8,					// 1/8
	PLAY_SPEED_SLOW_X16,				// 1/16
	PLAY_SPEED_FAST_X2,					// x2
	PLAY_SPEED_FAST_X4,					// x4
	PLAY_SPEED_FAST_X8,					// x8
	PLAY_SPEED_FAST_X16,				// x16
	PLAY_SPEED_REWIND_X2,				// -2x
	PLAY_SPEED_REWIND_X4,				// -4x
	PLAY_SPEED_REWIND_X8,				// -8x	
	PLAY_SPEED_REWIND_X16,				// -16x
	PLAY_SPEED_SINGLE_FRAME,			//��֡����,�ֶ�����
}PLAY_SPEED_ENUM;

//�����豸��Ϣ
#define		MAX_MIXER_DEVICE_NUM		16
typedef struct __MIXER_DEVICE_INFO_T
{
	int		id;
	char	name[128];
	char	version[16];
}MIXER_DEVICE_INFO_T;

//������������
typedef enum __AUDIO_ALARM_TYPE_ENUM
{
	AUDIO_ALARM_TYPE_BEEP		=	0x00000000,		//������
	AUDIO_ALARM_TYPE_WAV		=	0x00000001,		//wav�ļ�
	AUDIO_ALARM_TYPE_VOICE							//����
}AUDIO_ALARM_TYPE_ENUM;
typedef struct __AUDIO_TTS_VOICE_PACKET
{
	int			id;
	char		name[128];
}AUDIO_TTS_VOICE_PACKET;

//֡��Ϣ
typedef struct 
{
	unsigned int	codec;			//�����ʽ
	unsigned char	type;			//֡����
	unsigned char	fps;			//֡��
	unsigned char	reserved1;
	unsigned char	reserved2;

	unsigned short	width;			//��
	unsigned short  height;			//��
	unsigned int	sample_rate;	//������
	unsigned int	channels;		//����
	unsigned int	bitsPerSample;	//��������
	unsigned int	length;			//֡��С
	unsigned int    rtptimestamp_sec;	//rtp timestamp	sec
	unsigned int    rtptimestamp_usec;	//rtp timestamp	usec
	unsigned int	timestamp_sec;	//��
	
	float			bitrate;		//Kbps
	float			losspacket;
	//float			currentPlayTime;//��ǰ����ʱ��
}LIVE_FRAME_INFO;


//��Ƶ�ɼ��豸��Ϣ
typedef struct __LIVE_AUDIO_CAPTURE_DEVICE_INFO
{
	int			id;
	//LPGUID		lpGuid;
	//LPTSTR		lpstrDescription;
	//LPTSTR		lpstrModule;

	char		description[128];
	char		module[128];
}LIVE_AUDIO_CAPTURE_DEVICE_INFO;
//��Ƶ�ɼ���ʽ
typedef struct __LIVE_AUDIO_WAVE_FORMAT_INFO
{
    WORD        wFormatTag;         /* format type */
    WORD        nChannels;          /* number of channels (i.e. mono, stereo...) */
    DWORD       nSamplesPerSec;     /* sample rate */
    DWORD       nAvgBytesPerSec;    /* for buffer estimation */
    WORD        nBlockAlign;        /* block size of data */
    WORD        wBitsPerSample;     /* number of bits per sample of mono data */
    WORD        cbSize;             /* the count in bytes of the size of */
                                    /* extra information (after cbSize) */
}LIVE_AUDIO_WAVE_FORMAT_INFO;


typedef enum __LIVE_CALLBACK_TYPE_ENUM
{
	EASY_TYPE_CONNECTING		=	100,			//��ǰͨ��������
	EASY_TYPE_CONNECTED,							//��ǰͨ��������
	EASY_TYPE_RECONNECT,							//��ǰͨ�������ѶϿ�,��������
	EASY_TYPE_DISCONNECT,							//��ǰͨ����������ֹ(�ڲ������߳����˳�),ָ�������Ӵ���������»�ص���ֵ

	EASY_TYPE_CODEC_DATA,							//��������
	EASY_TYPE_DECODE_DATA,							//��������
	EASY_TYPE_SNAPSHOT,								//ץ��
	EASY_TYPE_RECORDING,							//¼��
	EASY_TYPE_INSTANT_REPLAY_RECORDING,				//��ʱ�ط�¼�����
	EASY_TYPE_PLAYBACK_TIME,						//��ǰ�ط�ʱ��
	EASY_TYPE_METADATA,

	EASY_TYPE_START_PLAY_AUDIO,						//��ʼ��������
	EASY_TYPE_STOP_PLAY_AUDIO,						//ֹͣ��������
	EASY_TYPE_CAPTURE_AUDIO_DATA,					//���زɼ�����Ƶ����

	EASY_TYPE_FILE_DURATION							//�ļ�ʱ��

}EASY_CALLBACK_TYPE_ENUM;
typedef int (CALLBACK *EasyPlayerCallBack)(EASY_CALLBACK_TYPE_ENUM callbackType, int channelId, void *userPtr, int mediaType, char *pbuf, LIVE_FRAME_INFO *frameInfo);


//���������
typedef void *PLAYER_HANDLE;

#ifdef __cplusplus
extern "C"
{
#endif

	/*
	libEasyPlayer ��Ϊ���ֵ��÷�ʽ:
								1. ʹ��libEasyPlayer_Initialize��ʼ��,  �ں�������е�����, PLAYER_HANDLEΪNULL, ��������libEasyPlayer_Deinitialize
								2. ʹ��libEasyPlayer_Create ����һ��PLAYER_HANDLE���, �ں�������е�����, ���ϴ����ľ��, ��������libEasyPlayer_Release
	*/

	//=====================================================================================
	//=====================================================================================
	//��ʼ��
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_Initialize(int supportMaxChannel/*����ָ�����ͨ����, ����ܳ����궨��MAX_CHANNEL_NUM*/);
	//����ʼ��
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_Deinitialize();

	//=====================================================================================
	//=====================================================================================
	//����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_Create(PLAYER_HANDLE *handle, int supportMaxChannel/*����ָ�����ͨ����, ����ܳ����궨��MAX_CHANNEL_NUM*/);
	//�ͷ�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_Release(PLAYER_HANDLE *handle);

	//=====================================================================================
	//=====================================================================================

	//����, ����һ��channelId, �������в����������ڸ�channelId
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_OpenStream(PLAYER_HANDLE handle, 
											LIVE_CHANNEL_SOURCE_TYPE_ENUM channelType/*ͨ��Դ����*/, 
											const char *url, unsigned char rtpOverTcp/*1Ϊtcp, 0Ϊudp*/, 
											const char *username, const char *password, 
											unsigned int mediaType, //ý������ MEDIA_TYPE_VIDEO | MEDIA_TYPE_AUDIO | MEDIA_TYPE_EVENT
											EasyPlayerCallBack callback, void *userPtr, //�ص��������Զ���ָ��
											unsigned int reconnection/*1��ʾ���޴�����,0��ʾ������,����1��ʾָ����������(��С��1000)*/, 
											unsigned int heartbeatType/*0*/, 
											unsigned int queueSize/*������д�С,�����1024*512 */, 
											unsigned char multiplex/*0x01:����Դ,����ͬһ��urlʱ����ǰ�˵�����ֻ��һ��  0x00:�򿪶��ٸ�url,���ж��ٸ�����*/);
	//�ر���
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_CloseStream(PLAYER_HANDLE handle, int channelId);

	//��ʼ����     ��ͬһ����,��󲥷Ÿ������ܴ���5��, ���ֻ���� libEasyPlayer_OpenStream �������� libEasyPlayer_StartPlayStream ���޴�����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StartPlayStream(PLAYER_HANDLE handle, int channelId, HWND hWnd, 
													RENDER_FORMAT renderFormat, unsigned char decodeType=0/*0:��� 1:Ӳ��*/);
	//�ͱ�������ָ��ͨ��, �����libEasyPlayer_OpenStream�е�channelType==LIVE_CHANNEL_SOURCE_TYPE_ENCODE_DATA
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_PutFrameData(PLAYER_HANDLE handle, int channelId, int mediaType, LIVE_FRAME_INFO *frameInfo, unsigned char *pbuf);
	//���֡����, ������һ���յ��Ĺؼ�֡��ʼ����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_ResetFrameQueue(PLAYER_HANDLE handle, int channelId);
	//ֹͣ����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StopPlayStream(PLAYER_HANDLE handle, int channelId);

	//��ȡָ��ͨ����ý����Ϣ
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_GetStreamInfo(PLAYER_HANDLE handle, int channelId, LIVE_MEDIA_INFO_T *pMediaInfo);

	//���ò���֡����, 1 - 10   ֡��ԽС��ʾ��ʱԽС
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetPlayFrameCache(PLAYER_HANDLE handle, int channelId, int cache/*�����С  1 - 10*/);
	//��ȡ����֡����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_GetPlayFrameCache(PLAYER_HANDLE handle, int channelId);



	//��ʾͳ����Ϣ
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_ShowStatisticalInfo(PLAYER_HANDLE handle, int channelId, unsigned char show);
	//�����Ƿ��������ʾ�ؼ�֡
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetDecodeType(PLAYER_HANDLE handle, int channelId, unsigned char decodeKeyframeOnly);
	//������Ƶ��ת
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetVideoFlip(PLAYER_HANDLE handle, int channelId, unsigned char flip);
	//������ʾ����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetRenderRect(PLAYER_HANDLE handle, int channelId, LPRECT lpRect);	//RECTΪ�ֱ��������
	//��������ʾ
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetScaleDisplay(PLAYER_HANDLE handle, int channelId, 
														unsigned char scaleDisplay/*0x00:�������� 0x01:��������ʾ*/,
														COLORREF bkColor/*����ɫ*/);
	//���õ�������
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetOverlayText(PLAYER_HANDLE handle, int channelId, const char *text);
	//��յ�������
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_ClearOverlayText(PLAYER_HANDLE handle, int channelId);



	//============================================================
	//��ʼ�ֶ�¼��  ���ָ����¼���ļ���С,��¼��ʱ����Ч����filesizeΪ0, ��duration��Ч
	//���preRecording����Ϊ1, ����Ӧ���ļ���С���ļ�ʱ����������Ԥ¼�Ĵ�С��ʱ��, ��: ָ��filesizeΪ100MB,ͬʱpreRecording����Ϊ1, ��ʵ��¼���ļ���СΪ100MB+Ԥ¼��С
	//Ԥ¼��С��ʱ�������ڲ�ָ��Ϊ10��,����Ӧ�ڴ����libEasyPlayer_OpenStream�е�queueSizeָ��, ��:�ڴ�����㹻�����Ԥ¼ʱ��Ϊ10��, �ڴ����С,Ԥ¼ʱ������10��
	//   ע:   ��������ʱ�ط�ʱ���������ֶ�¼��, ���᷵��-3
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StartRecording(PLAYER_HANDLE handle, int channelId, const char *foldername, const char *filename, 
														unsigned int filesize/*¼���ļ���С MB*/, int duration/*¼��ʱ��(second)*/,  
														unsigned char preRecording/*0x01:Ԥ¼  0x00:��Ԥ¼*/);
	//ֹͣ�ֶ�¼��
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StopRecording(PLAYER_HANDLE handle, int channelId);

	//ץͼ���ļ�, ֻ�����첽ץͼģʽ�£�����ʹ�ö���,�����ڴ�Ϊ31104000bytes(��ԼΪ32MB)
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SnapshotToFile(PLAYER_HANDLE handle, int channelId, unsigned char imageFormat/*0:bmp 1:jpg*/, 
														char *filename, unsigned char sync=0/*0:�첽: 1:ͬ��*/, 
														unsigned char useQueue=0/*1:ʹ�ö��� 0:��ʹ�ö���*/);

	//ץͼ���ڴ�  �ֽ�֧��RGB, �ڴ�ռ�������߷���
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SnapshotToMemory(PLAYER_HANDLE handle, int channelId, unsigned char imageFormat/*0:rgb 1:jpg*/, 
														unsigned char *out_imageData, int *out_imageSize, 
														int *out_width, int *out_height);


	//==============================================================================
	//==============================================================================
	//================���ӷŴ����==================================================
	//==============================================================================
	//==============================================================================
	//���÷Ŵ���ʼ��   fXPercent �� fYPercent Ϊ��굥���ĵ�����ڴ��ڵİٷֱ�   showBoxΪ�Ƿ���ʾ�����Ŀ�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetElectronicZoomStartPoint(PLAYER_HANDLE handle, int channelId, float fXPercent, float fYPercent, unsigned char showBox);
	//���÷Ŵ������
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetElectronicZoomEndPoint(PLAYER_HANDLE handle, int channelId, float fXPercent, float fYPercent);
	//�����Ƿ�Ŵ�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetElectronicZoom(PLAYER_HANDLE handle, int channelId, int zoomIn/*1:�Ŵ�  0:���Ŵ�*/);
	//����Ŵ����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_ResetElectronicZoom(PLAYER_HANDLE handle, int channelId);

	
	//==============================================================================
	//==============================================================================
	//================��ʱ�طż�����================================================
	//==============================================================================
	//==============================================================================
	//��ʼ��ʱ�ط�    �����ǰ�����ֶ�¼����, ���ܿ�����ʱ�ط�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_InstantReplay_Start(PLAYER_HANDLE handle, int channelId);
	//��ͣ��ʱ�ط�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_InstantReplay_Pause(PLAYER_HANDLE handle, int channelId);
	//�ָ���ʱ�ط�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_InstantReplay_Resume(PLAYER_HANDLE handle, int channelId);
	//ֹͣ��ʱ�ط�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_InstantReplay_Stop(PLAYER_HANDLE handle, int channelId);
	//���漴ʱ�ط�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_InstantReplay_Save(PLAYER_HANDLE handle, int channelId, char *filename/*�����ļ���������·��*/);
	//��һ֡
	//LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_InstantReplay_PreviousFrame(PLAYER_HANDLE handle, int channelId);
	//��һ֡
	//LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_InstantReplay_NextFrame(PLAYER_HANDLE handle, int channelId);
	//��ȡ��ʱ�ط��е�֡��
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_InstantReplay_GetFrameNum(PLAYER_HANDLE handle, int channelId, int *currentFrameNo, int *totalFrameNum);



	//==============================================================================
	//==============================================================================
	//==========����Ϊ�������ż�����================================================
	//==============================================================================
	//==============================================================================
	//��������
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StartPlaySound(PLAYER_HANDLE handle, int channelId);
	//ֹͣ��������
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StopPlaySound(PLAYER_HANDLE handle);
	//��ȡ��������״̬: �Ƿ��ڲ�����		0:������, <0:�ǲ�����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SoundPlaying(PLAYER_HANDLE handle, int channelId);


	//��ȡ��Ƶ�豸�б�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_GetAudioOutputDeviceList(PLAYER_HANDLE handle, MIXER_DEVICE_INFO_T	**devicelist, int *deviceNum);
	//���õ�ǰ��Ƶ�豸ID
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetAudioOutputDeviceId(PLAYER_HANDLE handle, int deviceId);
	//���õ�ǰ��Ƶ�豸����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetAudioOutputDeviceName(PLAYER_HANDLE handle, char *deviceName);

	//�������� ( 0 ~ 100 )
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_SetAudioVolume(PLAYER_HANDLE handle, int volume);
	//��ȡ����
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_GetAudioVolume(PLAYER_HANDLE handle);





	//==============================================================================
	//==============================================================================
	//==========����Ϊ�����ɼ�����==================================================
	//==============================================================================
	//==============================================================================
	//��ȡ��ǰ��Ƶ�ɼ��豸
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_GetAudioCaptureDeviceList(PLAYER_HANDLE handle, int *deviceNum, LIVE_AUDIO_CAPTURE_DEVICE_INFO **pDeviceInfo);
	//����Ƶ�ɼ��豸 && ��ȡ֧�ֵĸ�ʽ�б�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_OpenAudioCaptureDevice(PLAYER_HANDLE handle, int captureDeviceIndex, 
																			int *waveFormatNum, LIVE_AUDIO_WAVE_FORMAT_INFO **ppWaveFormatEx);
	//��ʼ��Ƶ�ɼ�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StartAudioCaptureById(PLAYER_HANDLE handle, int waveFormatExIndex, unsigned int codec, int frameSize, 
																			EasyPlayerCallBack callback, void *userptr);
	//��ʼ��Ƶ�ɼ�  �Զ���ɼ���ʽ
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StartAudioCaptureByParam(PLAYER_HANDLE handle, 
																			unsigned int codec/*��������: RTSP_AUDIO_CODEC_G711A  RTSP_AUDIO_CODEC_G711U RTSP_AUDIO_CODEC_AAC*/, 
																			int frameSize/*֡��С, g711ʱΪ160,320, aacʱΪ1024��2048*/, 
																			int samplerate/*������*/, int bitsPerSample/*��������*/, int channels/*ͨ��*/, 
																			EasyPlayerCallBack callback, void *userptr);
	//ֹͣ��Ƶ�ɼ�
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_StopAudioCapture(PLAYER_HANDLE handle);
	//�ر���Ƶ�ɼ��豸
	LIB_LIVEPLAYER_API int LIB_APICALL	libEasyPlayer_CloseAudioCaptureDevice(PLAYER_HANDLE handle);




#ifdef __cplusplus
}
#endif


#if 0

//�ص�����ʾ������:

int CALLBACK __LivePlayerCallBack(EASY_CALLBACK_TYPE_ENUM callbackType, int channelId, void *userPtr, int mediaType, char *pbuf, LIVE_FRAME_INFO *frameInfo)
{
	LIVE_VIDEO_T	*pLiveVideo = (LIVE_VIDEO_T *)userPtr;

	if (callbackType == EASY_TYPE_CODEC_DATA)	//��������
	{
		_TRACE(TRACE_LOG_DEBUG, "��������[ch%d]type[%d] channelId[%d] mediaType[%d] [%d x %d] framesize[%d]\n",  pLiveVideo->channelId,
			callbackType, channelId, mediaType, frameInfo->width, frameInfo->height, frameInfo->length);
	}
	else if (callbackType == EASY_TYPE_DECODE_DATA)
	{
		_TRACE(TRACE_LOG_DEBUG, "��������[ch%d]type[%d] channelId[%d] mediaType[%d] [%d x %d] framesize[%d]\n",  pLiveVideo->channelId,
			callbackType, channelId, mediaType, frameInfo->width, frameInfo->height, frameInfo->length);
	}
	else if (callbackType == EASY_TYPE_SNAPSHOT)
	{
		//ץ��ʱ, �ص���frameInfoΪNULL
		//mediaTypeΪMEDIA_TYPE_VIDEOʱ��ʾ�ɹ���ΪMEDIA_TYPE_EVENTʱ��ʾʧ��
		//pbufΪץ�ĵ��ļ���

		if (mediaType == MEDIA_TYPE_VIDEO)		//ץͼ�ɹ�
			_TRACE(TRACE_LOG_DEBUG, "ץ��ͼƬ�ɹ�[ch%d] %s. filename:%s\n",  channelId, mediaType==MEDIA_TYPE_VIDEO?"�ɹ�":"ʧ��", pbuf);
		else  if (mediaType == MEDIA_TYPE_EVENT)	//ץͼʧ��
			_TRACE(TRACE_LOG_DEBUG, "ץ��ͼƬʧ��[ch%d] %s. filename:%s\n",  channelId, mediaType==MEDIA_TYPE_VIDEO?"�ɹ�":"ʧ��", pbuf);
	}
	else if (callbackType == EASY_TYPE_RECORDING)
	{
		if (mediaType == MEDIA_TYPE_VIDEO)		//¼��ɹ�
			_TRACE(TRACE_LOG_DEBUG, "�ֶ�¼��ɹ�[ch%d] %s. filename:%s\n",  channelId, mediaType==MEDIA_TYPE_VIDEO?"�ɹ�":"ʧ��", pbuf);
		else  if (mediaType == MEDIA_TYPE_EVENT)	//¼��ʧ��
			_TRACE(TRACE_LOG_DEBUG, "�ֶ�¼��ʧ��[ch%d] %s. filename:%s\n",  channelId, mediaType==MEDIA_TYPE_VIDEO?"�ɹ�":"ʧ��", pbuf);
	}
	else if (callbackType == EASY_TYPE_PLAYBACK_TIME)		//�ط�ʱ��
	{
		char szTime[64] = {0};
		time_t tt = frameInfo->timestamp_sec;
		struct tm *_timetmp = NULL;
		_timetmp = localtime(&tt);
		if (NULL != _timetmp)	strftime(szTime, 32, "%Y-%m-%d %H:%M:%S ", _timetmp);

		_TRACE(TRACE_LOG_DEBUG, "[ch%d]��ǰ�ط�ʱ��: %s\n", channelId, szTime);
	}


	return 0;
}





#endif



#endif
