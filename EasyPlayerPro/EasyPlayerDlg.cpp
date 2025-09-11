#include "stdafx.h"
#include "EasyPlayer.h"
#include "EasyPlayerDlg.h"
#include "afxdialogex.h"
//#include "gui_common.h"
#include "xmlConfig.h"

#ifdef _DEBUG
#define new DEBUG_NEW
#endif

#pragma comment(lib, "libEasyPlayer/libEasyPlayer.lib")

// ����Ӧ�ó��򡰹��ڡ��˵���� CAboutDlg �Ի���

class CAboutDlg : public CDialogEx
{
public:
	CAboutDlg();

// �Ի�������
	enum { IDD = IDD_ABOUTBOX };

	protected:
	virtual void DoDataExchange(CDataExchange* pDX);    // DDX/DDV ֧��

// ʵ��
protected:
	DECLARE_MESSAGE_MAP()
};

CAboutDlg::CAboutDlg() : CDialogEx(CAboutDlg::IDD)
{
}

void CAboutDlg::DoDataExchange(CDataExchange* pDX)
{
	CDialogEx::DoDataExchange(pDX);
}

BEGIN_MESSAGE_MAP(CAboutDlg, CDialogEx)
END_MESSAGE_MAP()


// CLivePlayerDlg �Ի���




CLivePlayerDlg::CLivePlayerDlg(CWnd* pParent /*=NULL*/)
	: CDialogEx(CLivePlayerDlg::IDD, pParent)
{
	m_hIcon = AfxGetApp()->LoadIcon(IDR_MAINFRAME);

	InitialComponents();
}

void CLivePlayerDlg::DoDataExchange(CDataExchange* pDX)
{
	CDialogEx::DoDataExchange(pDX);
}

BEGIN_MESSAGE_MAP(CLivePlayerDlg, CDialogEx)
	ON_WM_SYSCOMMAND()
	ON_WM_PAINT()
	ON_WM_QUERYDRAGICON()
	ON_MESSAGE(WM_WINDOW_MAXIMIZED, OnWindowMaximized)
	ON_CBN_SELCHANGE(IDC_COMBO_SPLIT_SCREEN, &CLivePlayerDlg::OnCbnSelchangeComboSplitScreen)
	ON_CBN_SELCHANGE(IDC_COMBO_RENDER_FORMAT, &CLivePlayerDlg::OnCbnSelchangeComboRenderFormat)
	ON_BN_CLICKED(IDC_CHECK_SHOWNTOSCALE, &CLivePlayerDlg::OnBnClickedCheckShowntoscale)
	ON_WM_MOUSEWHEEL()
	ON_BN_CLICKED(IDC_CHECKMULTIPLEX, &CLivePlayerDlg::OnBnClickedCheckmultiplex)
	ON_BN_CLICKED(IDC_CHECK_FULLSCREEN, &CLivePlayerDlg::OnBnClickedCheckFullscreen)
	ON_BN_CLICKED(IDC_CHECK_DECODE_KEYFRAME, &CLivePlayerDlg::OnBnClickedCheckDecodeKeyframe)
	ON_STN_CLICKED(IDC_STATIC_COPYRIGHT, &CLivePlayerDlg::OnStnClickedStaticCopyright)
	ON_BN_CLICKED(IDC_BUTTON_OPEN_ALL, &CLivePlayerDlg::OnBnClickedButtonOpenAll)
END_MESSAGE_MAP()


// CLivePlayerDlg ��Ϣ�������

BOOL CLivePlayerDlg::OnInitDialog()
{
	CDialogEx::OnInitDialog();

	// ��������...���˵�����ӵ�ϵͳ�˵��С�

	// IDM_ABOUTBOX ������ϵͳ���Χ�ڡ�
	ASSERT((IDM_ABOUTBOX & 0xFFF0) == IDM_ABOUTBOX);
	ASSERT(IDM_ABOUTBOX < 0xF000);

	CMenu* pSysMenu = GetSystemMenu(FALSE);
	if (pSysMenu != NULL)
	{
		BOOL bNameValid;
		CString strAboutMenu;
		bNameValid = strAboutMenu.LoadString(IDS_ABOUTBOX);
		ASSERT(bNameValid);
		if (!strAboutMenu.IsEmpty())
		{
			pSysMenu->AppendMenu(MF_SEPARATOR);
			pSysMenu->AppendMenu(MF_STRING, IDM_ABOUTBOX, strAboutMenu);
		}
	}

	// ���ô˶Ի����ͼ�ꡣ��Ӧ�ó��������ڲ��ǶԻ���ʱ����ܽ��Զ�
	//  ִ�д˲���
	SetIcon(m_hIcon, TRUE);			// ���ô�ͼ��
	SetIcon(m_hIcon, FALSE);		// ����Сͼ��

	// TODO: �ڴ���Ӷ���ĳ�ʼ������
	SetBackgroundColor(RGB(0x5b,0x5b,0x5b));
	MoveWindow(0, 0, 1200, 640);

	CreateComponents();

	PRO_CONFIG_T	proConfig;
	XMLConfig		xmlConfig;
	memset(&proConfig, 0x00, sizeof(PRO_CONFIG_T));
	xmlConfig.LoadConfig(XML_CONFIG_FILENAME, &proConfig);


	if (NULL!=pVideoWindow)		pVideoWindow->channels		=	proConfig.splitWindow;
	if (NULL != pComboxSplitScreen)
	{
		if (4 == proConfig.splitWindow)	pComboxSplitScreen->SetCurSel(0);
		else if (8 == proConfig.splitWindow)	pComboxSplitScreen->SetCurSel(1);
		else if (9 == proConfig.splitWindow)	pComboxSplitScreen->SetCurSel(2);
		else if (16 == proConfig.splitWindow)	pComboxSplitScreen->SetCurSel(3);
		else if (36 == proConfig.splitWindow)	pComboxSplitScreen->SetCurSel(4);
		else if (64 == proConfig.splitWindow)	pComboxSplitScreen->SetCurSel(5);
	}


	if (NULL!=pChkShownToScale)		pChkShownToScale->SetCheck(proConfig.scale);
	if (NULL!=pChkMultiplex)		pChkMultiplex->SetCheck(proConfig.multiple);
	if (NULL!=pChkFullScreen)		pChkFullScreen->SetCheck(proConfig.fullScreen);
	if (proConfig.fullScreen==0x01)
	{
		FullScreen();
	}

	if (NULL != pVideoWindow && NULL!=pVideoWindow->pDlgVideo)
	{
		const char url_header[4][16] = {"rtsp://", "rtmp://", "http://", "file://"};
		int idx = 0;
		for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
		{
			pVideoWindow->pDlgVideo[i].SetURL((char *)url_header[idx++], 0, 1, 1, 1, 3, 1, 0);

			if (idx>=4)	idx = 0;
		}

		int cfg_channel_num = sizeof(proConfig.channel)/sizeof(proConfig.channel[0]);
		for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
		{
			if (i>=cfg_channel_num)		break;

			if ( (int)strlen(proConfig.channel[i].url) < 10)		continue;

			pVideoWindow->pDlgVideo[i].SetURL(proConfig.channel[i].url, 
				proConfig.scale, proConfig.channel[i].showOSD, 
				proConfig.channel[i].protocol, proConfig.multiple, 
				proConfig.channel[i].cache, proConfig.channel[i].showToolbar,
				proConfig.channel[i].autoPlay);
		}
		/*
		FILE *f = fopen("url.txt", "rb");
		if (NULL != f)
		{
			int idx = 0;
			char szURL[128] = {0};
			while (! feof(f) && idx+1<_SURV_MAX_WINDOW_NUM)
			{
				memset(szURL, 0x00, sizeof(szURL));
				fgets(szURL, sizeof(szURL), f);

				if (0 != strcmp(szURL, "\0"))
				{
					pVideoWindow->pDlgVideo[idx++].SetURL(szURL);
				}
			}
		}
		*/
	}


	char szTime[64] = {0};
	time_t tt = time(NULL);
	struct tm *_timetmp = NULL;
	_timetmp = localtime(&tt);
	if (NULL != _timetmp)	strftime(szTime, 32, "%Y-%m-%d %H:%M:%S ", _timetmp);

	char szTitle[128] = {0};
	wchar_t wszTitle[256] = {0};

	sprintf(szTitle, "LivePlayer  StartupTime: %s", szTime);
	MByteToWChar(szTitle, wszTitle, sizeof(wszTitle)/sizeof(wszTitle[0]));
	//SetWindowText(wszTitle);

	OnCbnSelchangeComboRenderFormat();

	return TRUE;  // ���ǽ��������õ��ؼ������򷵻� TRUE
}

void CLivePlayerDlg::OnSysCommand(UINT nID, LPARAM lParam)
{
	if ((nID & 0xFFF0) == IDM_ABOUTBOX)
	{
		CAboutDlg dlgAbout;
		dlgAbout.DoModal();
	}
	else
	{
		CDialogEx::OnSysCommand(nID, lParam);
	}
}

// �����Ի��������С����ť������Ҫ����Ĵ���
//  �����Ƹ�ͼ�ꡣ����ʹ���ĵ�/��ͼģ�͵� MFC Ӧ�ó���
//  �⽫�ɿ���Զ���ɡ�

void CLivePlayerDlg::OnPaint()
{
	if (IsIconic())
	{
		CPaintDC dc(this); // ���ڻ��Ƶ��豸������

		SendMessage(WM_ICONERASEBKGND, reinterpret_cast<WPARAM>(dc.GetSafeHdc()), 0);

		// ʹͼ���ڹ����������о���
		int cxIcon = GetSystemMetrics(SM_CXICON);
		int cyIcon = GetSystemMetrics(SM_CYICON);
		CRect rect;
		GetClientRect(&rect);
		int x = (rect.Width() - cxIcon + 1) / 2;
		int y = (rect.Height() - cyIcon + 1) / 2;

		// ����ͼ��
		dc.DrawIcon(x, y, m_hIcon);
	}
	else
	{
		CDialogEx::OnPaint();
	}
}

//���û��϶���С������ʱϵͳ���ô˺���ȡ�ù��
//��ʾ��
HCURSOR CLivePlayerDlg::OnQueryDragIcon()
{
	return static_cast<HCURSOR>(m_hIcon);
}

BOOL CLivePlayerDlg::DestroyWindow()
{
	libEasyPlayer_Release(&playerHandle);
	DeleteComponents();

	return CDialogEx::DestroyWindow();
}


LRESULT CLivePlayerDlg::WindowProc(UINT message, WPARAM wParam, LPARAM lParam)
{
	if (WM_PAINT == message || WM_SIZE==message)
	{
		UpdateComponents();
	}

	return CDialogEx::WindowProc(message, wParam, lParam);
}



void	CLivePlayerDlg::InitialComponents()
{
	pComboxSplitScreen	=	NULL;
	pComboxRenderFormat	=	NULL;
	pVideoWindow		=	NULL;
	pChkShownToScale	=	NULL;
	pChkMultiplex		=	NULL;
	pChkFullScreen		=	NULL;
	pStaticCopyright	=	NULL;
	pChkOnlyDecodeKeyframe	=	NULL;
	pBtnOpenAll			=	NULL;

	RenderFormat	=	RENDER_FORMAT_RGB24_GDI;//RGB565

	libEasyPlayer_Create(&playerHandle, 128);

}

void	CLivePlayerDlg::CreateComponents()
{
	__CREATE_WINDOW(pComboxSplitScreen, CComboBox,		IDC_COMBO_SPLIT_SCREEN);
	__CREATE_WINDOW(pComboxRenderFormat, CComboBox,		IDC_COMBO_RENDER_FORMAT);
	__CREATE_WINDOW(pChkShownToScale, CButton,		IDC_CHECK_SHOWNTOSCALE);
	__CREATE_WINDOW(pChkMultiplex, CButton,		IDC_CHECKMULTIPLEX);
	__CREATE_WINDOW(pChkFullScreen, CButton,		IDC_CHECK_FULLSCREEN);
	__CREATE_WINDOW(pChkOnlyDecodeKeyframe, CButton,		IDC_CHECK_DECODE_KEYFRAME);
	__CREATE_WINDOW(pBtnOpenAll, CButton,		IDC_BUTTON_OPEN_ALL);
	__CREATE_WINDOW(pStaticCopyright, CStatic,		IDC_STATIC_COPYRIGHT);

	pStaticCopyright->ShowWindow(FALSE);
	SetWindowText(TEXT("Mr.Jack.202510"));

	if (NULL != pChkShownToScale)		pChkShownToScale->SetWindowText(TEXT("��������ʾ"));
	if (NULL != pChkMultiplex)			pChkMultiplex->SetWindowText(TEXT("����Դ"));
	if (NULL != pChkFullScreen)			pChkFullScreen->SetWindowText(TEXT("ȫ��"));
	if (pChkOnlyDecodeKeyframe)		pChkOnlyDecodeKeyframe->SetWindowText(TEXT("������ؼ�֡"));
	if (pBtnOpenAll)								pBtnOpenAll->SetWindowText(TEXT("Play All"));

	if (NULL == pVideoWindow)
	{
		pVideoWindow = new VIDEO_NODE_T;
		pVideoWindow->fullscreen    = false;
		pVideoWindow->maximizedId	=	-1;
		pVideoWindow->selectedId	=	-1;
		pVideoWindow->channels		=	4;
		if (pVideoWindow->channels>_SURV_MAX_WINDOW_NUM)	pVideoWindow->channels=_SURV_MAX_WINDOW_NUM;
		pVideoWindow->pDlgVideo	=	new CDlgVideo[_SURV_MAX_WINDOW_NUM];//gAppInfo.maxchannels
		for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
		{
			pVideoWindow->pDlgVideo[i].Create(IDD_DIALOG_VIDEO, this);
			pVideoWindow->pDlgVideo[i].SetWindowId(i);
			pVideoWindow->pDlgVideo[i].ShowWindow(SW_HIDE);
		}
	}

	if (NULL != pComboxSplitScreen)
	{
		pComboxSplitScreen->AddString(TEXT("4����"));
		pComboxSplitScreen->AddString(TEXT("8����"));
		pComboxSplitScreen->AddString(TEXT("9����"));
		pComboxSplitScreen->AddString(TEXT("16����"));
		pComboxSplitScreen->AddString(TEXT("36����"));
		pComboxSplitScreen->AddString(TEXT("64����"));
		pComboxSplitScreen->SetCurSel(0);
	}
	if (NULL != pComboxRenderFormat)
	{
		pComboxRenderFormat->AddString(TEXT("YV12"));
		pComboxRenderFormat->AddString(TEXT("YUY2"));
		pComboxRenderFormat->AddString(TEXT("RGB565"));
		pComboxRenderFormat->AddString(TEXT("X8R8G8B8"));
		pComboxRenderFormat->AddString(TEXT("RGB24"));
		pComboxRenderFormat->AddString(TEXT("RGB32"));

		pComboxRenderFormat->SetCurSel(4);
		//pComboxRenderFormat->SetCurSel(0);
	}
}
void	CLivePlayerDlg::UpdateComponents()
{
	CRect	rcClient;
	GetClientRect(&rcClient);
	if (rcClient.IsRectEmpty())		return;

	CRect	rcVideo;
	rcVideo.SetRect(rcClient.left, rcClient.top, rcClient.right, rcClient.bottom-30);
	UpdateVideoPosition(&rcVideo);

	CRect	rcSplitScreen;
	rcSplitScreen.SetRect(rcClient.left+5, rcVideo.bottom+3, rcClient.left+100, rcVideo.bottom+3+90);
	__MOVE_WINDOW(pComboxSplitScreen, rcSplitScreen);

	CRect	rcRenderFormat;
	rcRenderFormat.SetRect(rcSplitScreen.right+5, rcSplitScreen.top, 
										rcSplitScreen.right+5+100, rcSplitScreen.bottom);
	//__MOVE_WINDOW(pComboxRenderFormat, rcRenderFormat);

	CRect	rcShownToScale;
	rcShownToScale.SetRect(rcRenderFormat.right+10, rcRenderFormat.top, 
										rcRenderFormat.right+10+110, rcRenderFormat.top+30);
	//__MOVE_WINDOW(pChkShownToScale, rcShownToScale);

	CRect	rcMultiplex;
	rcMultiplex.SetRect(rcShownToScale.right+10, rcShownToScale.top, 
									rcShownToScale.right+10+70, rcShownToScale.bottom);
	//__MOVE_WINDOW(pChkMultiplex, rcMultiplex);

	CRect	rcFullScreen;
	rcFullScreen.SetRect(rcMultiplex.right+10, rcMultiplex.top, 
									rcMultiplex.right+10+70, rcMultiplex.bottom);
	//__MOVE_WINDOW(pChkFullScreen, rcFullScreen);

	CRect	rcDecodeKeyFrame;
	rcDecodeKeyFrame.SetRect(rcFullScreen.right+10, rcFullScreen.top, 
									rcFullScreen.right+10+120, rcFullScreen.bottom);
	//__MOVE_WINDOW(pChkOnlyDecodeKeyframe, rcDecodeKeyFrame);


	CRect	rcCopyright;
	rcCopyright.SetRect(rcClient.right-200, rcSplitScreen.top+5, 
									rcClient.right-2, rcClient.bottom);
	__MOVE_WINDOW(pStaticCopyright, rcCopyright);

	CRect	rcOpenAll;
	int btnWidth = 120;
	int margin = 10;
	// Position the Open All button flush to the right edge of the client area
	rcOpenAll.SetRect(rcClient.right - btnWidth - margin, rcFullScreen.top,
					rcClient.right - margin, rcFullScreen.bottom - 5);
	__MOVE_WINDOW(pBtnOpenAll, rcOpenAll);
}
void	CLivePlayerDlg::DeleteComponents()
{
	if (NULL != pVideoWindow)
	{
		if (NULL != pVideoWindow->pDlgVideo)
		{
			for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
			{
				pVideoWindow->pDlgVideo[i].DestroyWindow();
			}
			delete []pVideoWindow->pDlgVideo;
			pVideoWindow->pDlgVideo = NULL;
		}
		delete pVideoWindow;
		pVideoWindow = NULL;
	}
}


void	CLivePlayerDlg::UpdateVideoPosition(LPRECT lpRect)
{
	CRect rcClient;
	if (NULL == lpRect)
	{
		GetClientRect(&rcClient);
		lpRect = &rcClient;
	}

	if (NULL == pVideoWindow)		return;

	//CRect rcClient;
	rcClient.CopyRect(lpRect);

	CRect rcTmp;
	rcTmp.SetRect(rcClient.left, rcClient.top, rcClient.left+rcClient.Width()/2, rcClient.top+rcClient.Height()/2);

	//

	if (pVideoWindow->maximizedId==-1)
	{
		int nTimes = 2;
		int nLeft = lpRect->left;
		int nTop  = lpRect->top;

		for (int i=pVideoWindow->channels; i<_SURV_MAX_WINDOW_NUM; i++)
		{
			if (pVideoWindow->pDlgVideo[i].IsWindowVisible())
				pVideoWindow->pDlgVideo[i].ShowWindow(SW_HIDE);
		}

		switch (pVideoWindow->channels)
		{
		case 4:
		case 9:
		case 16:
		case 25:
		case 36:
		case 64:
		default:
			{
				nTimes = 2;
				if (pVideoWindow->channels == 4)		nTimes	=	2;
				if (pVideoWindow->channels == 9)		nTimes	=	3;
				if (pVideoWindow->channels == 16)		nTimes	=	4;
				if (pVideoWindow->channels == 25)		nTimes	=	5;
				if (pVideoWindow->channels == 36)		nTimes	=	6;
				if (pVideoWindow->channels == 64)		nTimes	=	8;

				RECT rcTmp;
				SetRectEmpty(&rcTmp);

				int n = 0;//videoPatrol.patrolStartId;
				for (int i = 0; i < nTimes; i++)
				{
					for (int j = 0; j < nTimes; j ++)
					{
						//SetRect(&rcTmp, nLeft, nTop, nLeft + imgSize.cx / nTimes, nTop + imgSize.cy / nTimes);
						SetRect(&rcTmp, nLeft, nTop, nLeft + rcClient.Width() / nTimes, nTop + rcClient.Height() / nTimes);
						//CopyRect(&vidRenderHandle[n].drawvid.rect, &rcTmp);

						if (j+1==nTimes && rcTmp.right<rcClient.right)
						{
							rcTmp.right = rcClient.right;
						}
						if (i+1==nTimes && rcTmp.bottom<rcClient.bottom)
						{
							rcTmp.bottom = rcClient.bottom;
						}


						pVideoWindow->pDlgVideo[n].MoveWindow(&rcTmp);
						if (! pVideoWindow->pDlgVideo[n].IsWindowVisible())
							pVideoWindow->pDlgVideo[n].ShowWindow(SW_SHOW);


						n ++;

						nLeft += rcClient.Width() / nTimes;
					}
					nLeft = rcClient.left;
					nTop  += (rcClient.Height()) / nTimes;
				}
			}
			break;
		case 6:		//6��??��
			{
				int nWidth = rcClient.Width() / 3;
				int nHeight= rcClient.Height()/ 3;

				int nRight = 0;
				int nBottom= 0;
				if (rcClient.right > nWidth*3)	nRight = rcClient.Width()-nWidth*3;
				if (rcClient.bottom> nHeight*3)	nBottom= rcClient.Height()-nHeight*3;
			
				nLeft = rcClient.left;
				nTop  = rcClient.top+nHeight*2;
				for (int i=3; i<6; i++)
				{
					rcTmp.SetRect(nLeft, nTop, nLeft+nWidth, nTop+nHeight);
					if (i+1==6)			rcTmp.right += nRight;
					if (nBottom > 0)	rcTmp.bottom += nBottom;
					pVideoWindow->pDlgVideo[i].MoveWindow(&rcTmp);
					if (! pVideoWindow->pDlgVideo[i].IsWindowVisible())
						pVideoWindow->pDlgVideo[i].ShowWindow(SW_SHOW);
				
					nLeft += nWidth;
				}
				nLeft -= nWidth;
				nTop  = rcClient.top;
				for (int i=1; i<3; i++)
				{
					rcTmp.SetRect(nLeft, nTop, nLeft+nWidth, nTop+nHeight);
					if (nRight>0)	rcTmp.right += nRight;
					pVideoWindow->pDlgVideo[i].MoveWindow(&rcTmp);
					if (! pVideoWindow->pDlgVideo[i].IsWindowVisible())
						pVideoWindow->pDlgVideo[i].ShowWindow(SW_SHOW);
					nTop += nHeight;
				}
			
				rcTmp.SetRect(rcClient.left, rcClient.top, rcTmp.left, rcTmp.bottom);
				pVideoWindow->pDlgVideo[0].MoveWindow(&rcTmp);
				if (! pVideoWindow->pDlgVideo[0].IsWindowVisible())
					pVideoWindow->pDlgVideo[0].ShowWindow(SW_SHOW);
			}
			break;
		case 8:		//8����
			{

				int nWidth = rcClient.Width() / 4;
				int nHeight= rcClient.Height()/ 4;

				int nRight = 0;
				int nBottom= 0;
				if (rcClient.right > nWidth*4)	nRight = rcClient.Width()-nWidth*4;
				if (rcClient.bottom> nHeight*4)	nBottom= rcClient.Height()-nHeight*4;

				nLeft = rcClient.left;
				nTop  = rcClient.top+nHeight*3;
				for (int i=4; i<8; i++)
				{
					rcTmp.SetRect(nLeft, nTop, nLeft+nWidth, nTop+nHeight);
					if (i+1==8)			rcTmp.right += nRight;
					if (nBottom > 0)	rcTmp.bottom += nBottom;
					pVideoWindow->pDlgVideo[i].MoveWindow(&rcTmp);
					if (! pVideoWindow->pDlgVideo[i].IsWindowVisible())
							pVideoWindow->pDlgVideo[i].ShowWindow(SW_SHOW);

					nLeft += nWidth;
				}
				nLeft -= nWidth;
				nTop  = rcClient.top;
				for (int i=1; i<4; i++)
				{
					rcTmp.SetRect(nLeft, nTop, nLeft+nWidth, nTop+nHeight);
					if (nRight>0)	rcTmp.right += nRight;
					pVideoWindow->pDlgVideo[i].MoveWindow(&rcTmp);
					if (! pVideoWindow->pDlgVideo[i].IsWindowVisible())
						pVideoWindow->pDlgVideo[i].ShowWindow(SW_SHOW);
					nTop += nHeight;
				}

				rcTmp.SetRect(rcClient.left, rcClient.top, rcTmp.left, rcTmp.bottom);
				pVideoWindow->pDlgVideo[0].MoveWindow(&rcTmp);
				if (! pVideoWindow->pDlgVideo[0].IsWindowVisible())
					pVideoWindow->pDlgVideo[0].ShowWindow(SW_SHOW);

			}
			break;
		}

		for (int vid=0; vid<_SURV_MAX_WINDOW_NUM; vid++)
		{
			//pVideoWindow->pDlgVideo[vid].SetSelectedChannel(pVideoWindow->selectedId==vid);
		}
	}
	else
	{
		for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
		{
			if (pVideoWindow->pDlgVideo[i].IsWindowVisible() && i!=pVideoWindow->maximizedId)
			{
				pVideoWindow->pDlgVideo[i].ShowWindow(SW_HIDE);
			}
		}
		rcTmp.SetRect(lpRect->left, lpRect->top, lpRect->right, lpRect->bottom);
		pVideoWindow->pDlgVideo[pVideoWindow->maximizedId].MoveWindow(&rcTmp);
		pVideoWindow->pDlgVideo[pVideoWindow->maximizedId].ShowWindow(SW_SHOW);
	}
}



LRESULT CLivePlayerDlg::OnWindowMaximized(WPARAM wParam, LPARAM lParam)
{
	int nCh = (int)wParam;

	if (pVideoWindow->maximizedId == -1)
	{
		pVideoWindow->maximizedId = nCh;
	}
	else
	{
		pVideoWindow->maximizedId = -1;
	}
	UpdateComponents();

	return 0;
}




void CLivePlayerDlg::OnCbnSelchangeComboSplitScreen()
{
	if (NULL == pVideoWindow)		return;

	int nSplitWindow = 4;
	int nIdx = pComboxSplitScreen->GetCurSel();
	if (nIdx == 0)	nSplitWindow = 4;
	else if (nIdx == 1)	nSplitWindow = 8;
	else if (nIdx == 2)	nSplitWindow = 9;
	else if (nIdx == 3)	nSplitWindow = 16;
	else if (nIdx == 4)	nSplitWindow = 36;
	else if (nIdx == 5)	nSplitWindow = 64;

	pVideoWindow->channels		=	nSplitWindow;
	UpdateComponents();
}


void CLivePlayerDlg::OnCbnSelchangeComboRenderFormat()
{
	if (NULL == pComboxRenderFormat)		return;

	int iIdx = pComboxRenderFormat->GetCurSel();
	if (iIdx == 0)	RenderFormat	=	RENDER_FORMAT_YV12;//YV12
	else if (iIdx == 1)	RenderFormat	=	RENDER_FORMAT_YUY2;//YUY2
	else if (iIdx == 2)	RenderFormat	=	RENDER_FORMAT_RGB565;//RGB565
	else if (iIdx == 3)	RenderFormat	=	RENDER_FORMAT_X8R8G8B8;//X8R8G8B8
	else if (iIdx == 4)	RenderFormat	=	RENDER_FORMAT_RGB24_GDI;//RGB24
	else if (iIdx == 5)	RenderFormat	=	RENDER_FORMAT_RGB32_GDI;//RGB32
}


void CLivePlayerDlg::OnBnClickedCheckShowntoscale()
{
	//IDC_CHECK_SHOWNTOSCALE
	if (NULL == pVideoWindow)					return;
	if (NULL == pVideoWindow->pDlgVideo)		return;

	int shownToScale = pChkShownToScale->GetCheck();
	//static int shownToScale = 0x00;
	//shownToScale = (shownToScale==0x00?0x01:0x00);

	for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
	{
		pVideoWindow->pDlgVideo[i].SetShownToScale(shownToScale);
	}
}

void CLivePlayerDlg::OnBnClickedCheckmultiplex()
{
	if (NULL == pVideoWindow)					return;
	if (NULL == pVideoWindow->pDlgVideo)		return;

	unsigned char multiplex = (unsigned char)pChkMultiplex->GetCheck();

	for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
	{
		pVideoWindow->pDlgVideo[i].SetMultiplex(multiplex);
	}
}
void CLivePlayerDlg::OnBnClickedCheckDecodeKeyframe()
{
	if (NULL == pVideoWindow)					return;
	if (NULL == pVideoWindow->pDlgVideo)		return;

	unsigned char ucDecodeType = (unsigned char)pChkOnlyDecodeKeyframe->GetCheck();

	for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
	{
		pVideoWindow->pDlgVideo[i].SetDecodeType(ucDecodeType);
	}
}

BOOL CLivePlayerDlg::OnMouseWheel(UINT nFlags, short zDelta, CPoint pt)
{
	POINT	point;
	point.x = pt.x;
	point.y = pt.y;

	//ScreenToClient(&point);

	//TRACE("CLivePlayerDlg::OnMouseWheel  zDelta: %d  pt.x[%d] pt.y[%d]\n", zDelta, point.x, point.y);

	if (NULL != pVideoWindow && NULL != pVideoWindow->pDlgVideo)
	{
		for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
		{
			if (! pVideoWindow->pDlgVideo[i].IsWindowVisible() )	continue;

			CRect rcVideo;
			pVideoWindow->pDlgVideo[i].GetWindowRect(&rcVideo);
			//TRACE("Window[%d]  L:%d\tT:%d\tR:%d\tB:%d\n", i, rcVideo.left, rcVideo.top, rcVideo.right, rcVideo.bottom);

			if (PtInRect(&rcVideo, point))
			{
				//TRACE("���λ�ڵ�[%d]������.\n", i);

				pVideoWindow->pDlgVideo[i].OnMouseWheel(zDelta, pt);

				break;
			}

		}
	}

	return CDialogEx::OnMouseWheel(nFlags, zDelta, pt);
}





void	CLivePlayerDlg::FullScreen()
{
	INT		x, y, w, h;
	DWORD dwStyle = GetWindowLong( this->m_hWnd, GWL_STYLE );

	static bool bFullScreen = false;

	bFullScreen = !bFullScreen;
	if (bFullScreen)
	{
		x = 0;
		y = 0;
		w = GetSystemMetrics(SM_CXSCREEN);
		h = GetSystemMetrics(SM_CYSCREEN);

		// ȥ��������  
		ModifyStyle(WS_CAPTION, 0); 
		 // ȥ���߿�
		ModifyStyleEx(WS_EX_DLGMODALFRAME, 0);  
		//����λ�úʹ�С����ԭ������
		SetWindowPos(NULL, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED); 
		//��󻯴���
		ShowWindow(SW_MAXIMIZE);
	}
	else
	{
		ModifyStyle(0, WS_CAPTION);
		ModifyStyleEx(0, WS_EX_DLGMODALFRAME);
		//SetWindowPos(NULL, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED);
		ShowWindow(SW_NORMAL);
	}

}


void CLivePlayerDlg::OnBnClickedCheckFullscreen()
{
	FullScreen();
}





void CLivePlayerDlg::OnStnClickedStaticCopyright()
{
	// TODO: Add your control notification handler code here
}


void CLivePlayerDlg::OnBnClickedButtonOpenAll()
{
	static bool bOpenAll = false;
	if (NULL == pVideoWindow)					return;
	if (NULL == pVideoWindow->pDlgVideo)		return;

	bOpenAll = !bOpenAll;

	for (int i=0; i<_SURV_MAX_WINDOW_NUM; i++)
	{
		pVideoWindow->pDlgVideo[i].OnBnClickedButtonPreview();
	}
}
