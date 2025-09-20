#pragma once

#include "DlgVideo.h"

#define	_SURV_MAX_WINDOW_NUM		64

typedef struct __VIDEO_NODE_T
{
	bool		fullscreen;
	int			maximizedId;
	int			selectedId;
	int			channels;
	CDlgVideo	*pDlgVideo;
}VIDEO_NODE_T;

// CLivePlayerDlg �Ի���
class CLivePlayerDlg : public CDialogEx
{
// ����
public:
	CLivePlayerDlg(CWnd* pParent = NULL);	// ��׼���캯��


public:
	CComboBox		*pComboxSplitScreen;
	CComboBox		*pComboxRenderFormat;	//IDC_COMBO_RENDER_FORMAT
	VIDEO_NODE_T	*pVideoWindow;		//��Ƶ����
	CButton			*pChkShownToScale;	//��������ʾ
	CButton			*pChkMultiplex;		//Դ����	IDC_CHECKMULTIPLEX
	CButton			*pChkFullScreen;	//IDC_CHECK_FULLSCREEN
	CStatic			*pStaticCopyright;	//IDC_STATIC_COPYRIGHT
	CButton			*pChkOnlyDecodeKeyframe;	//IDC_CHECK_DECODE_KEYFRAME
	CButton			*pBtnOpenAll;		//IDC_BUTTON_OPEN_ALL

	void	InitialComponents();
	void	CreateComponents();
	void	UpdateComponents();
	void	DeleteComponents();
	void	UpdateVideoPosition(LPRECT lpRect);
	void	FullScreen();

// �Ի�������
	enum { IDD = IDD_PLAYER_DIALOG };

	protected:
	virtual void DoDataExchange(CDataExchange* pDX);	// DDX/DDV ֧��


// ʵ��
protected:
	HICON m_hIcon;

	// ���ɵ���Ϣӳ�亯��
	virtual BOOL OnInitDialog();
	afx_msg void OnSysCommand(UINT nID, LPARAM lParam);
	afx_msg void OnPaint();
	afx_msg HCURSOR OnQueryDragIcon();
	DECLARE_MESSAGE_MAP()
	LRESULT OnWindowMaximized(WPARAM wParam, LPARAM lParam);
public:
	virtual BOOL DestroyWindow();
	virtual LRESULT WindowProc(UINT message, WPARAM wParam, LPARAM lParam);
	afx_msg void OnCbnSelchangeComboSplitScreen();
	afx_msg void OnCbnSelchangeComboRenderFormat();
	afx_msg void OnBnClickedCheckShowntoscale();
	afx_msg BOOL OnMouseWheel(UINT nFlags, short zDelta, CPoint pt);
	afx_msg void OnBnClickedCheckmultiplex();
	afx_msg void OnBnClickedCheckFullscreen();
	afx_msg void OnBnClickedCheckDecodeKeyframe();
	afx_msg void OnStnClickedStaticCopyright();
	afx_msg void OnBnClickedButtonOpenAll();
};
