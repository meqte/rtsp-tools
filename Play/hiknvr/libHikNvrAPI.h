#ifndef __LIB_HIK_NVR_API_H__
#define __LIB_HIK_NVR_API_H__



#define WIN32_LEAN_AND_MEAN
#define LIBHIKNVR_API __declspec(dllexport)
#include <windows.h>


typedef struct __DEVICE_TIME_T
{
    unsigned long ulYear;		//��
    unsigned long ulMonth;		//��
    unsigned long ulDay;		//��
    unsigned long ulHour;		//ʱ
    unsigned long ulMinute;		//��
    unsigned long ulSecond;		//��
}DEVICE_TIME_T;


typedef struct __NVR_CHANNEL_INFO_T
{
	//int		enable;
	char	name[36];
	char	ip[16];
	int		port;
}NVR_CHANNEL_INFO_T;

typedef void *HIKNVR_HANDLE;			//����NVR���


typedef void(CALLBACK *HIKNVR_CallBack) (LONG lPlayHandle, DWORD dwDataType, BYTE *pBuffer,DWORD dwBufSize,void *pUser);

#ifdef __cplusplus
extern "C"
{
#endif

	//��ʼ��
	int LIBHIKNVR_API	libHIKNVR_Init(HIKNVR_HANDLE *handle);
	//����ʼ��
	int LIBHIKNVR_API	libHIKNVR_Deinit(HIKNVR_HANDLE *handle);

	//��¼
	int LIBHIKNVR_API	libHIKNVR_Login(HIKNVR_HANDLE handle, char *ipaddr, int port, char *username, char *password);
	//�ǳ�
	int LIBHIKNVR_API	libHIKNVR_Logout(HIKNVR_HANDLE handle);

	//��ȡ����ͨ����Ϣ
	int LIBHIKNVR_API	libHIKNVR_GetChannelList(HIKNVR_HANDLE handle, int *channelNum, NVR_CHANNEL_INFO_T **pChannelInfo);
	//����ͨ��ID��ȡ��Ӧͨ����Ϣ
	int LIBHIKNVR_API	libHIKNVR_GetChannelInfoById(HIKNVR_HANDLE handle, const int channelid, NVR_CHANNEL_INFO_T *pChannelInfo);
	//�������IP��ȡ��Ӧ��ͨ��ID
	int LIBHIKNVR_API	libHIKNVR_GetChannelIdByCameraIP(HIKNVR_HANDLE handle, const char *cameraIP, int *channelId);

	//�������»�ȡָ��ͨ����¼������
	int LIBHIKNVR_API	libHIKNVR_GetRecordingDateByYearMonth(HIKNVR_HANDLE handle, const int channelid, const int year, const int month, unsigned char pDate[]);
	//�������ں�ͨ��ID, ��ȡ��Ӧ��¼��ʱ���б�
	int LIBHIKNVR_API	libHIKNVR_GetRecordingTimeByChannelId(HIKNVR_HANDLE handle, const int channelid, const int iYear, const int iMonth, const int iDay, unsigned char *_timelist);


	//��ʼʵʱ��
	long LIBHIKNVR_API	libHIKNVR_StartRealStream(HIKNVR_HANDLE handle, const int channelId, int streamType, HIKNVR_CallBack callback, void *userptr);
	//ֹͣʵʱ��
	int	LIBHIKNVR_API	libHIKNVR_StopRealStream(HIKNVR_HANDLE handle, long realStreamHandle);



	//----------------------------------------------------------------
	//��ʼ�ط�, ���ػطž��
	long LIBHIKNVR_API	libHIKNVR_StartPlayback(HIKNVR_HANDLE handle, const int channelid, DEVICE_TIME_T *startTime, DEVICE_TIME_T *endTime, HWND hWnd);
	//��ͣ�ط�
	int LIBHIKNVR_API	libHIKNVR_PausePlayback(HIKNVR_HANDLE handle, long playbackHandle);
	//�����ط�
	int LIBHIKNVR_API	libHIKNVR_ResumePlayback(HIKNVR_HANDLE handle, long playbackHandle);
	//ֹͣ�ط�
	int LIBHIKNVR_API	libHIKNVR_StopPlayback(HIKNVR_HANDLE handle, long playbackHandle);


	//��ʼ�ط���, ���ػطž��
	long LIBHIKNVR_API	libHIKNVR_StartPlaybackStream(HIKNVR_HANDLE handle, const int channelid, DEVICE_TIME_T *startTime, DEVICE_TIME_T *endTime, 
																			HIKNVR_CallBack callback, void *userptr);
	//�رջط���
	int LIBHIKNVR_API	libHIKNVR_StopPlaybackStream(HIKNVR_HANDLE handle, long playbackHandle);



#ifdef __cplusplus
}
#endif


#endif
