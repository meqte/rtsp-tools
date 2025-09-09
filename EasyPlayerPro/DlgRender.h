#pragma once


//#define ENABLE_IVA_MODULE		0x00

typedef struct __CHANNEL_STATUS
{
	int			audio;
	int			recordingMpg;
	int			recordingES;
	int			recordingDebug;
	int			decodeKeyframeOnly;
	int			instantReplay;
	int			instantReplaySave;
	int			playSpeed;				//�����ٶ�

	char		filenameES[260];
	char		filenameDebug[260];
	FILE		*fES;
	FILE		*fDebug;

	int			setRenderRect;
	int			flip;
	int			digitalZoom;
	//int			videoAnalysis;
	//int			warningMode;
	int			drag;

	int			faceMatchThreshold;		// �����ȶԷ�ֵ

	int			U10_Zoom;
	int			u10ZoomTally;

	int			zoneId;
}CHANNELSTATUS;
// CDlgRender �Ի���

class CDlgRender : public CDialogEx
{
	DECLARE_DYNAMIC(CDlgRender)

public:
	CDlgRender(CWnd* pParent = NULL);   // ��׼���캯��
	virtual ~CDlgRender();

	void	ResetChannel();


	void	SetChannelId(int _channelId)	{mChannelId = _channelId;}
	void	OnMouseWheel(short zDelta, CPoint pt);
	void	SetRecordingFlag(int flag);

	void	onVideoData(int channelId, int mediaType, char *pbuf, LIVE_FRAME_INFO *frameInfo);

	int		mChannelId;
	CHANNELSTATUS	channelStatus;
	HMENU	hMenu;
	void	ClosePopupMenu();

	bool	mDrag;
	POINT	startPoint;
	int		scaleMultiple;	//���ű���
	POINT	pt_start;
	POINT	pt_start_org;

	float base_left_percent;
	float base_right_percent;
	float	fWidthPercent;
	float base_top_percent;
	float base_bottom_percent;
	float fHeightPercent;

	void	InitZoom();

	void	LoadZones();

// �Ի�������
	enum { IDD = IDD_DIALOG_RENDER };

protected:
	virtual void DoDataExchange(CDataExchange* pDX);    // DDX/DDV ֧��

	DECLARE_MESSAGE_MAP()
public:
	afx_msg void OnLButtonDblClk(UINT nFlags, CPoint point);
	afx_msg void OnRButtonUp(UINT nFlags, CPoint point);
	virtual BOOL OnCommand(WPARAM wParam, LPARAM lParam);
	afx_msg void OnLButtonDown(UINT nFlags, CPoint point);
	afx_msg void OnLButtonUp(UINT nFlags, CPoint point);
	afx_msg void OnMouseMove(UINT nFlags, CPoint point);
	afx_msg BOOL OnMouseWheel(UINT nFlags, short zDelta, CPoint pt);
	afx_msg void OnSize(UINT nType, int cx, int cy);
	virtual BOOL OnInitDialog();
};
